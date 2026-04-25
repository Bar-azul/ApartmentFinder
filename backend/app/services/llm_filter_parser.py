from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from app.config import settings
from app.models.search_filters import SearchFilters


class LLMFilterParser:
    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None

    def parse(self, prompt: str) -> SearchFilters:
        if not self.client:
            return self._fallback_parse(prompt)

        system_prompt = """
        אתה ממיר בקשת חיפוש דירה בעברית ל-JSON בלבד.

        החזר רק JSON תקין בלי markdown ובלי הסברים.

        השדות האפשריים:
        {
          "city_text": string|null,
          "city_texts": string[],
          "minPrice": number|null,
          "maxPrice": number|null,
          "minRooms": number|null,
          "maxRooms": number|null,
          "must_have": string[],
          "exclude": string[],
          "imageOnly": 1,
          "priceOnly": 1,
          "region": 1,
          "zoom": 11
        }

        חוקים:
        - אם יש כמה ערים, החזר אותן בתוך city_texts.
        - אם יש עיר אחת בלבד, אפשר להחזיר גם city_text וגם city_texts עם אותה עיר.
        - אם המשתמש אומר "עד 3500" זה maxPrice.
        - אם המשתמש אומר "מ-4000 עד 5500" אז minPrice=4000 ו-maxPrice=5500.
        - אם המשתמש אומר "בין 2.5 ל-4 חדרים" אז minRooms=2.5 ו-maxRooms=4.
        - אם המשתמש אומר "לא קרקע" או "לא קומת קרקע" הכנס ל-exclude את ground_floor.
        - אם המשתמש מבקש ממד הכנס ל-must_have את mamad.
        - אם המשתמש מבקש מעלית הכנס ל-must_have את elevator.
        - אם המשתמש מבקש חניה הכנס ל-must_have את parking.
        - אם אין מידע, החזר null או מערך ריק.
        """

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=f"{system_prompt}\n\nבקשת המשתמש:\n{prompt}",
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )

            data = self._safe_json_loads(response.text)
            filters = SearchFilters(**data)
            filters.raw_prompt = prompt

            self._apply_known_city_mapping(filters)
            self._apply_default_map_scope(filters)

            return filters

        except Exception:
            return self._fallback_parse(prompt)

    def _safe_json_loads(self, text: str | None) -> dict[str, Any]:
        if not text:
            return {}

        cleaned = text.strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        return json.loads(cleaned)

    def _fallback_parse(self, prompt: str) -> SearchFilters:
        filters = SearchFilters(raw_prompt=prompt)

        price_match = re.search(r"עד\s*(\d{3,6})", prompt)
        if price_match:
            filters.maxPrice = int(price_match.group(1))

        min_price_match = re.search(r"מעל\s*(\d{3,6})", prompt)
        if min_price_match:
            filters.minPrice = int(min_price_match.group(1))

        rooms_range_match = re.search(r"בין\s*(\d+(?:\.\d+)?)\s*ל[-\s]*(\d+(?:\.\d+)?)\s*חדר", prompt)
        if rooms_range_match:
            filters.minRooms = float(rooms_range_match.group(1))
            filters.maxRooms = float(rooms_range_match.group(2))
        else:
            rooms_match = re.search(r"(\d+(?:\.\d+)?)\s*חדר", prompt)
            if rooms_match:
                rooms = float(rooms_match.group(1))
                filters.minRooms = rooms
                filters.maxRooms = rooms

        known_cities = ["הרצליה", "רמת השרון", "בני ברק", "פתח תקווה", "גבעת שמואל", "נתניה"]
        for city in known_cities:
            if city in prompt:
                filters.city_text = city
                break

        self._apply_known_city_mapping(filters)
        self._apply_default_map_scope(filters)

        return filters

    def _apply_known_city_mapping(self, filters: SearchFilters) -> None:
        city_map = {
            "הרצליה": {
                "multiCity": "0417",
                "multiArea": "18",
                "multiNeighborhood": "413",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "רמת השרון": {
                "multiArea": "18",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "בני ברק": {
                "multiArea": "18",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "גבעת שמואל": {
                "multiArea": "18",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "פתח תקווה": {
                "multiArea": "18",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "נתניה": {
                "multiArea": "78",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
        }

        if filters.city_text in city_map:
            for key, value in city_map[filters.city_text].items():
                setattr(filters, key, value)

    def _apply_default_map_scope(self, filters: SearchFilters) -> None:
        filters.region = filters.region or 1
        filters.imageOnly = 1
        filters.priceOnly = 1
        filters.zoom = filters.zoom or 11

        if not filters.bBox:
            filters.bBox = "32.077494,34.791048,32.294470,34.872168"