from __future__ import annotations

from collections import Counter
from typing import Any, Awaitable, Callable

import httpx

from app.config import settings
from app.models.apartment import Apartment
from app.models.search_filters import SearchFilters
from app.services.playwright_details_service import PlaywrightDetailsService
from app.services.yad2_location_resolver import Yad2LocationResolver


REGION_SLUG_BY_ID = {
    1: "center-and-sharon",
    2: "south",
    3: "tel-aviv",
    4: "jerusalem",
    5: "north",
    6: "haifa-and-north",
    7: "north",
}


ProgressCallback = Callable[[int, str], Awaitable[None]]


class Yad2Client:
    MAP_LIMIT_THRESHOLD = 190
    MAX_TILE_DEPTH = 5

    def __init__(self) -> None:
        self.base_url = settings.yad2_base_url.rstrip("/")
        self.www_base_url = "https://www.yad2.co.il"
        self.map_endpoint = "/realestate-feed/rent/map"

        self.details_service = PlaywrightDetailsService()
        self.location_resolver = Yad2LocationResolver()

    async def search_rentals(
        self,
        filters: SearchFilters,
        progress_callback: ProgressCallback | None = None,
    ) -> list[Apartment]:
        requested_cities = self.location_resolver.get_requested_cities(filters)

        if progress_callback:
            await progress_callback(18, "מתרגם מיקום לאזור חיפוש...")

        if len(requested_cities) > 1:
            apartments = await self._search_multiple_cities(
                base_filters=filters,
                city_names=requested_cities,
                progress_callback=progress_callback,
            )
        else:
            apartments = await self._search_single_city_or_general(
                filters=filters,
                progress_callback=progress_callback,
            )

        if progress_callback:
            await progress_callback(98, "מסיים ומחזיר תוצאות...")

        return apartments

    async def _search_multiple_cities(
        self,
        base_filters: SearchFilters,
        city_names: list[str],
        progress_callback: ProgressCallback | None = None,
    ) -> list[Apartment]:
        all_apartments: list[Apartment] = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for index, city_name in enumerate(city_names, start=1):
                location = await self.location_resolver.resolve_city_async(city_name)

                if not location:
                    print(f"Could not resolve city location for: {city_name}")
                    continue

                city_filters = base_filters.model_copy(deep=True)
                city_filters = self.location_resolver.apply_location_to_filters(
                    city_filters,
                    location,
                )

                if progress_callback:
                    await progress_callback(
                        20 + int((index - 1) / max(len(city_names), 1) * 15),
                        f"מחפש מודעות בעיר {location.city_name} ({index}/{len(city_names)})",
                    )

                city_apartments = await self._fetch_and_filter_from_map(
                    client=client,
                    filters=city_filters,
                    include_feature_filter=False,
                    debug_prefix=f"[{location.city_name}] ",
                )

                all_apartments.extend(city_apartments)

        all_apartments = self._deduplicate_apartments(all_apartments)

        print("TOTAL APARTMENTS AFTER MULTI CITY BASIC FILTER:", len(all_apartments))
        print("CITIES COUNT AFTER MULTI CITY BASIC FILTER:", Counter(a.city for a in all_apartments))

        if progress_callback:
            await progress_callback(
                35,
                f"לאחר סינון בסיסי נשארו {len(all_apartments)} מודעות",
            )

        all_apartments = await self._maybe_enrich_and_feature_filter(
            apartments=all_apartments,
            filters=base_filters,
            progress_callback=progress_callback,
        )

        return all_apartments

    async def _search_single_city_or_general(
        self,
        filters: SearchFilters,
        progress_callback: ProgressCallback | None = None,
    ) -> list[Apartment]:
        requested_cities = self.location_resolver.get_requested_cities(filters)

        if len(requested_cities) == 1:
            location = await self.location_resolver.resolve_city_async(requested_cities[0])

            if not location:
                print(f"Could not resolve city location for: {requested_cities[0]}")
                return []

            filters = filters.model_copy(deep=True)
            filters = self.location_resolver.apply_location_to_filters(filters, location)

        else:
            filters = filters.model_copy(deep=True)
            filters = await self.location_resolver.apply_location_filters(filters)

        if progress_callback:
            await progress_callback(20, "שולח בקשה ל־Yad2 Map API...")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            apartments = await self._fetch_and_filter_from_map(
                client=client,
                filters=filters,
                include_feature_filter=False,
                debug_prefix="",
            )

        if progress_callback:
            await progress_callback(
                35,
                f"לאחר סינון בסיסי נשארו {len(apartments)} מודעות",
            )

        apartments = await self._maybe_enrich_and_feature_filter(
            apartments=apartments,
            filters=filters,
            progress_callback=progress_callback,
        )

        return apartments

    async def _fetch_and_filter_from_map(
        self,
        client: httpx.AsyncClient,
        filters: SearchFilters,
        include_feature_filter: bool,
        debug_prefix: str = "",
    ) -> list[Apartment]:
        map_params = self._build_map_params(filters)

        print(f"{debug_prefix}YAD2 MAP PARAMS:", map_params)

        markers = await self._fetch_markers_adaptive(
            client=client,
            params=map_params,
            debug_prefix=debug_prefix,
        )

        apartments = [self._normalize_marker(marker) for marker in markers]
        apartments = self._deduplicate_apartments(apartments)

        print(f"{debug_prefix}TOTAL UNIQUE APARTMENTS FROM MAP:", len(apartments))
        print(f"{debug_prefix}CITIES COUNT BEFORE FILTER:", Counter(a.city for a in apartments))
        print(f"{debug_prefix}ALLOWED CITY FILTERS:", filters.city_texts, filters.city_text)

        apartments = self._post_filter(
            apartments=apartments,
            filters=filters,
            include_feature_filter=include_feature_filter,
        )

        apartments = self._deduplicate_apartments(apartments)

        print(f"{debug_prefix}TOTAL APARTMENTS AFTER BASIC FILTER:", len(apartments))
        print(f"{debug_prefix}CITIES COUNT AFTER BASIC FILTER:", Counter(a.city for a in apartments))

        return apartments

    async def _fetch_markers_adaptive(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        debug_prefix: str = "",
    ) -> list[dict[str, Any]]:
        bbox = params.get("bBox")

        if not bbox:
            markers, clusters = await self._fetch_markers_once(
                client=client,
                params=params,
                debug_prefix=debug_prefix,
            )

            print(f"{debug_prefix}YAD2 MARKERS:", len(markers))
            print(f"{debug_prefix}YAD2 CLUSTERS:", clusters)

            return markers

        all_markers = await self._fetch_bbox_recursive(
            client=client,
            params=params,
            bbox=str(bbox),
            depth=0,
            debug_prefix=debug_prefix,
        )

        unique_markers = self._deduplicate_markers(all_markers)

        print(f"{debug_prefix}YAD2 TOTAL MARKERS FROM TILES:", len(all_markers))
        print(f"{debug_prefix}YAD2 UNIQUE MARKERS FROM TILES:", len(unique_markers))

        return unique_markers

    async def _fetch_bbox_recursive(
            self,
            client: httpx.AsyncClient,
            params: dict[str, Any],
            bbox: str,
            depth: int,
            debug_prefix: str = "",
    ) -> list[dict[str, Any]]:
        tile_params = self._build_tile_params(
            base_params=params,
            bbox=bbox,
            depth=depth,
        )

        markers, clusters_count = await self._fetch_markers_once(
            client=client,
            params=tile_params,
            debug_prefix=debug_prefix,
        )

        print(
            f"{debug_prefix}TILE depth={depth} "
            f"bbox={bbox} markers={len(markers)} clusters={clusters_count}"
        )

        should_split = (
                len(markers) >= self.MAP_LIMIT_THRESHOLD
                and depth < self.MAX_TILE_DEPTH
                and self._can_split_bbox(bbox)
        )

        if not should_split:
            return markers

        result: list[dict[str, Any]] = []

        for child_bbox in self._split_bbox(bbox):
            child_markers = await self._fetch_bbox_recursive(
                client=client,
                params=params,
                bbox=child_bbox,
                depth=depth + 1,
                debug_prefix=debug_prefix,
            )
            result.extend(child_markers)

        return result

    def _build_tile_params(
            self,
            base_params: dict[str, Any],
            bbox: str,
            depth: int,
    ) -> dict[str, Any]:
        tile_params = dict(base_params)

        # חשוב:
        # כשמפצלים לפי bBox, לא שולחים city/area,
        # אחרת Yad2 מחזיר שוב את אותה תקרת 200 לפי העיר.
        tile_params.pop("city", None)
        tile_params.pop("area", None)
        tile_params.pop("multiCity", None)
        tile_params.pop("multiArea", None)
        tile_params.pop("multiNeighborhood", None)

        tile_params["bBox"] = bbox

        # ככל שה־tile קטן יותר, zoom גבוה יותר.
        current_zoom = int(tile_params.get("zoom") or 11)
        tile_params["zoom"] = max(current_zoom, 13 + depth)

        return tile_params

    async def _fetch_markers_once(
        self,
        client: httpx.AsyncClient,
        params: dict[str, Any],
        debug_prefix: str = "",
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            map_data = await self._get_json(
                client=client,
                endpoint=self.map_endpoint,
                params=params,
            )

            data = map_data.get("data", {})
            markers = data.get("markers", []) or []
            clusters = data.get("clusters", []) or []

            print(f"{debug_prefix}YAD2 DATA KEYS:", list(data.keys()))

            return markers, len(clusters)

        except Exception as e:
            print(f"{debug_prefix}YAD2 TILE REQUEST FAILED params={params} error={e}")
            return [], 0

    def _split_bbox(self, bbox: str) -> list[str]:
        min_lat, min_lon, max_lat, max_lon = self._parse_bbox(bbox)

        mid_lat = (min_lat + max_lat) / 2
        mid_lon = (min_lon + max_lon) / 2

        return [
            self._format_bbox(min_lat, min_lon, mid_lat, mid_lon),
            self._format_bbox(min_lat, mid_lon, mid_lat, max_lon),
            self._format_bbox(mid_lat, min_lon, max_lat, mid_lon),
            self._format_bbox(mid_lat, mid_lon, max_lat, max_lon),
        ]

    def _can_split_bbox(self, bbox: str) -> bool:
        try:
            min_lat, min_lon, max_lat, max_lon = self._parse_bbox(bbox)

            return (
                abs(max_lat - min_lat) > 0.001
                and abs(max_lon - min_lon) > 0.001
            )
        except Exception:
            return False

    def _parse_bbox(self, bbox: str) -> tuple[float, float, float, float]:
        parts = [float(part.strip()) for part in bbox.split(",")]

        if len(parts) != 4:
            raise ValueError(f"Invalid bbox: {bbox}")

        lat1, lon1, lat2, lon2 = parts

        min_lat = min(lat1, lat2)
        max_lat = max(lat1, lat2)
        min_lon = min(lon1, lon2)
        max_lon = max(lon1, lon2)

        return min_lat, min_lon, max_lat, max_lon

    def _format_bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
    ) -> str:
        return (
            f"{min_lat:.6f},"
            f"{min_lon:.6f},"
            f"{max_lat:.6f},"
            f"{max_lon:.6f}"
        )

    async def _maybe_enrich_and_feature_filter(
            self,
            apartments: list[Apartment],
            filters: SearchFilters,
            progress_callback: ProgressCallback | None = None,
    ) -> list[Apartment]:
        """
        Smart mode:
        - אם אין must_have: לא עושים enrichment בכלל.
        - אם יש must_have: מחזירים את כל המודעות מיד כ-pending.
        - בהמשך נעשה background enrichment הדרגתי.
        """

        if not filters.must_have:
            for apartment in apartments:
                apartment.verification_status = "not_required"
                apartment.required_features = []
                apartment.verification_reason = None

            print("ENRICH SKIPPED: no must_have filters")
            return apartments

        for apartment in apartments:
            apartment.verification_status = "pending"
            apartment.required_features = list(filters.must_have)
            apartment.verification_reason = "ממתין לאימות מאפיינים"

        print(
            "ENRICH DEFERRED:",
            f"apartments={len(apartments)}",
            f"must_have={filters.must_have}",
        )

        if progress_callback:
            await progress_callback(
                45,
                f"נמצאו {len(apartments)} מודעות מועמדות. מאפיינים יאומתו בהדרגה...",
            )

        return apartments

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = await client.get(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=self._api_headers(),
        )

        response.raise_for_status()
        return response.json()

    def _api_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            "origin": "https://www.yad2.co.il",
            "referer": "https://www.yad2.co.il/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/147.0.0.0 Safari/537.36"
            ),
        }

    def _build_map_params(self, filters: SearchFilters) -> dict[str, Any]:
        params: dict[str, Any] = {}

        internal_fields = {
            "city_text",
            "city_texts",
            "raw_prompt",
            "minRooms",
            "maxRooms",
            "must_have",
            "exclude",
            "multiCity",
            "multiArea",
            "multiNeighborhood",
        }

        for key, value in filters.model_dump(exclude_none=True).items():
            if key in internal_fields:
                continue

            if value == [] or value == "":
                continue

            params[key] = value

        return params

    def _normalize_marker(self, marker: dict[str, Any]) -> Apartment:
        address = marker.get("address") or {}
        details = marker.get("additionalDetails") or {}
        metadata = marker.get("metaData") or {}

        city = (address.get("city") or {}).get("text")
        neighborhood = (address.get("neighborhood") or {}).get("text")
        street = (address.get("street") or {}).get("text")
        house = address.get("house") or {}
        coords = address.get("coords") or {}
        property_data = details.get("property") or {}

        token = marker.get("token")

        return Apartment(
            order_id=marker.get("orderId"),
            ad_number=marker.get("adNumber"),
            token=token,
            price=marker.get("price"),
            rooms=details.get("roomsCount"),
            square_meter=details.get("squareMeter") or metadata.get("squareMeterBuild"),
            property_type=property_data.get("text"),
            description=metadata.get("description"),
            city=city,
            neighborhood=neighborhood,
            street=street,
            house_number=house.get("number"),
            floor=house.get("floor"),
            lat=coords.get("lat"),
            lon=coords.get("lon"),
            cover_image=metadata.get("coverImage"),
            images=metadata.get("images") or [],
            yad2_url=self._build_item_url(token, address),
        )

    def _build_item_url(
        self,
        token: str | None,
        address: dict[str, Any],
    ) -> str | None:
        if not token:
            return None

        region_id = ((address.get("region") or {}).get("id")) or 1
        region_slug = REGION_SLUG_BY_ID.get(region_id, "center-and-sharon")

        return f"{self.www_base_url}/realestate/item/{region_slug}/{token}"

    def _post_filter(
        self,
        apartments: list[Apartment],
        filters: SearchFilters,
        include_feature_filter: bool,
    ) -> list[Apartment]:
        result: list[Apartment] = []

        allowed_cities = {
            self._normalize_hebrew_text(city)
            for city in (filters.city_texts or [])
            if city
        }

        if filters.city_text:
            allowed_cities.add(self._normalize_hebrew_text(filters.city_text))

        for apartment in apartments:
            if apartment.property_type in {"חניה", "מחסן"}:
                continue

            if allowed_cities:
                apartment_city = self._normalize_hebrew_text(apartment.city or "")

                if apartment_city not in allowed_cities:
                    continue

            if filters.minPrice is not None and apartment.price is not None:
                if apartment.price < filters.minPrice:
                    continue

            if filters.maxPrice is not None and apartment.price is not None:
                if apartment.price > filters.maxPrice:
                    continue

            if filters.minRooms is not None and apartment.rooms is not None:
                if apartment.rooms < filters.minRooms:
                    continue

            if filters.maxRooms is not None and apartment.rooms is not None:
                if apartment.rooms > filters.maxRooms:
                    continue

            if "ground_floor" in filters.exclude and apartment.floor == 0:
                continue

            if include_feature_filter and filters.must_have:
                matches_all_features = all(
                    getattr(apartment.features, feature_name, False)
                    for feature_name in filters.must_have
                )

                if not matches_all_features:
                    continue

            result.append(apartment)

        return result

    def _deduplicate_apartments(self, apartments: list[Apartment]) -> list[Apartment]:
        seen: set[str] = set()
        result: list[Apartment] = []

        for apartment in apartments:
            key = str(apartment.order_id or apartment.token or apartment.ad_number or "")

            if not key:
                result.append(apartment)
                continue

            if key in seen:
                continue

            seen.add(key)
            result.append(apartment)

        return result

    def _deduplicate_markers(self, markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []

        for marker in markers:
            key = str(
                marker.get("orderId")
                or marker.get("token")
                or marker.get("adNumber")
                or ""
            )

            if not key:
                result.append(marker)
                continue

            if key in seen:
                continue

            seen.add(key)
            result.append(marker)

        return result

    def _normalize_hebrew_text(self, value: str) -> str:
        value = (value or "").strip()
        value = value.replace("״", '"').replace("׳", "'")
        value = value.replace("פתח תקוה", "פתח תקווה")
        value = value.replace("קריית אונו", "קרית אונו")
        value = value.replace("תל-אביב", "תל אביב")
        value = value.replace("זיכרון יעקב", "זכרון יעקב")
        value = value.replace("בת-ים", "בת ים")
        value = value.replace("באר-שבע", "באר שבע")
        value = value.replace("בארשבע", "באר שבע")
        return value