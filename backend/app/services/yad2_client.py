from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.models.apartment import Apartment
from app.models.search_filters import SearchFilters


class Yad2Client:
    def __init__(self) -> None:
        self.base_url = settings.yad2_base_url.rstrip("/")
        self.endpoint = "/realestate-feed/rent/map"

    async def search_rentals(self, filters: SearchFilters) -> list[Apartment]:
        params = self._build_params(filters)

        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.yad2.co.il",
            "referer": "https://www.yad2.co.il/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}{self.endpoint}",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        markers = data.get("data", {}).get("markers", [])
        apartments = [self._normalize_marker(marker) for marker in markers]

        return self._post_filter(apartments, filters)

    def _build_params(self, filters: SearchFilters) -> dict[str, Any]:
        params: dict[str, Any] = {}

        internal_fields = {
            "city_text",
            "city_texts",
            "raw_prompt",
            "minRooms",
            "maxRooms",
            "must_have",
            "exclude",
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
        order_id = marker.get("orderId")

        return Apartment(
            order_id=order_id,
            token=token,
            price=marker.get("price"),
            rooms=details.get("roomsCount"),
            square_meter=details.get("squareMeter"),
            property_type=property_data.get("text"),
            city=city,
            neighborhood=neighborhood,
            street=street,
            house_number=house.get("number"),
            floor=house.get("floor"),
            lat=coords.get("lat"),
            lon=coords.get("lon"),
            cover_image=metadata.get("coverImage"),
            images=metadata.get("images") or [],
            yad2_url=self._build_listing_url(token, order_id),
        )

    def _build_listing_url(self, token: str | None, order_id: int | None) -> str | None:
        if not order_id:
            return None

        return f"https://www.yad2.co.il/realestate/rent?keyword={order_id}"

        # כרגע לינק בסיסי. בהמשך נבדוק את מבנה הלינק המדויק של דף מודעה ביד2.
        query = urlencode({"token": token or "", "orderId": order_id or ""})
        return f"https://www.yad2.co.il/realestate/item?{query}"

    def _post_filter(
            self,
            apartments: list[Apartment],
            filters: SearchFilters,
    ) -> list[Apartment]:
        result: list[Apartment] = []

        allowed_cities = set(filters.city_texts or [])
        if filters.city_text:
            allowed_cities.add(filters.city_text)

        for apartment in apartments:
            if apartment.property_type in {"חניה", "מחסן"}:
                continue

            if allowed_cities:
                if not apartment.city or apartment.city not in allowed_cities:
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

            if "ground_floor" in filters.exclude:
                if apartment.floor == 0:
                    continue

            result.append(apartment)

        return result