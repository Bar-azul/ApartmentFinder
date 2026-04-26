from __future__ import annotations

from collections import Counter
from typing import Any

import httpx

from app.config import settings
from app.models.apartment import Apartment
from app.models.search_filters import SearchFilters
from app.services.playwright_details_service import PlaywrightDetailsService
from app.services.yad2_location_resolver import Yad2LocationResolver


REGION_SLUG_BY_ID = {
    1: "center-and-sharon",
    2: "south",
}


class Yad2Client:
    def __init__(self) -> None:
        self.base_url = settings.yad2_base_url.rstrip("/")
        self.www_base_url = "https://www.yad2.co.il"
        self.map_endpoint = "/realestate-feed/rent/map"
        self.details_service = PlaywrightDetailsService()
        self.location_resolver = Yad2LocationResolver()

    async def search_rentals(
        self,
        filters: SearchFilters,
        progress_callback=None,
    ) -> list[Apartment]:
        if progress_callback:
            await progress_callback(18, "מתרגם מיקום לאזור חיפוש...")

        filters = self.location_resolver.apply_location_filters(filters)

        if progress_callback:
            await progress_callback(20, "שולח בקשה ל־Yad2 Map API...")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            map_params = self._build_map_params(filters)
            print("YAD2 MAP PARAMS:", map_params)

            map_data = await self._get_json(client, self.map_endpoint, map_params)

        data = map_data.get("data", {})
        markers = data.get("markers", []) or []

        print("YAD2 MARKERS:", len(markers))
        print("YAD2 CLUSTERS:", len(data.get("clusters", []) or []))
        print("YAD2 DATA KEYS:", list(data.keys()))

        if progress_callback:
            await progress_callback(28, f"נמצאו {len(markers)} מודעות ראשוניות")

        apartments = [self._normalize_marker(marker) for marker in markers]

        print("TOTAL APARTMENTS FROM MARKERS:", len(apartments))
        print("CITIES COUNT BEFORE FILTER:", Counter(a.city for a in apartments))
        print("ALLOWED CITY FILTERS:", filters.city_texts, filters.city_text)

        apartments = self._post_filter(
            apartments=apartments,
            filters=filters,
            include_feature_filter=False,
        )

        print("TOTAL APARTMENTS AFTER BASIC FILTER:", len(apartments))
        print("CITIES COUNT AFTER BASIC FILTER:", Counter(a.city for a in apartments))

        if progress_callback:
            await progress_callback(35, f"לאחר סינון בסיסי נשארו {len(apartments)} מודעות")

        should_enrich = (
            settings.playwright_enabled
            and (
                settings.playwright_enrich_on_search
                or bool(filters.must_have)
            )
        )

        if should_enrich:
            apartments = await self.details_service.enrich_many(
                apartments=apartments,
                must_have=filters.must_have,
                progress_callback=progress_callback,
            )

            print("TOTAL APARTMENTS AFTER ENRICH:", len(apartments))
            print("CITIES COUNT AFTER ENRICH:", Counter(a.city for a in apartments))

            apartments = self._post_filter(
                apartments=apartments,
                filters=filters,
                include_feature_filter=bool(filters.must_have),
            )

            print("TOTAL APARTMENTS AFTER FEATURE FILTER:", len(apartments))
            print("CITIES COUNT AFTER FEATURE FILTER:", Counter(a.city for a in apartments))

        if progress_callback:
            await progress_callback(98, "מסיים ומחזיר תוצאות...")

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
            square_meter=details.get("squareMeter"),
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

    def _normalize_hebrew_text(self, value: str) -> str:
        value = (value or "").strip()
        value = value.replace("״", '"').replace("׳", "'")
        value = value.replace("פתח תקוה", "פתח תקווה")
        value = value.replace("קריית אונו", "קרית אונו")
        value = value.replace("תל-אביב", "תל אביב")
        value = value.replace("זיכרון יעקב", "זכרון יעקב")
        return value