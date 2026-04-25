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
        self.client = (
            genai.Client(api_key=settings.gemini_api_key)
            if settings.gemini_api_key
            else None
        )

    def parse(self, prompt: str) -> SearchFilters:
        if not self.client:
            return self._fallback_parse(prompt)

        system_prompt = """
אתה ממיר בקשת חיפוש דירה בעברית ל-JSON בלבד.

החזר רק JSON תקין.

השדות:
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
- אם יש כמה ערים -> city_texts
- אם עיר אחת -> city_text + city_texts
- עד 5500 = maxPrice
- מ-4000 עד 5500 = minPrice/maxPrice
- בין 2.5 ל-4 חדרים = minRooms/maxRooms
- ממד = mamad
- מעלית = elevator
- חניה = parking
- לא קרקע = ground_floor
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

        except Exception:
            filters = self._fallback_parse(prompt)

        filters.raw_prompt = prompt
        filters = self._post_process_prompt_rules(filters, prompt)
        self._apply_known_city_mapping(filters)
        self._apply_default_map_scope(filters)

        return filters

    def _safe_json_loads(self, text: str | None) -> dict[str, Any]:
        if not text:
            return {}

        cleaned = text.strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        return json.loads(cleaned)

    def _fallback_parse(self, prompt: str) -> SearchFilters:
        return SearchFilters(raw_prompt=prompt)

    def _post_process_prompt_rules(self, filters: SearchFilters, prompt: str) -> SearchFilters:
        known_cities = [
            "הרצליה",
            "פתח תקווה",
            "פתח תקוה",
            "קרית אונו",
            "קריית אונו",
            "רעננה",
            "כפר סבא",
            "רמת השרון",
            "בני ברק",
            "גבעת שמואל",
            "נתניה",
        ]

        found = []

        for city in known_cities:
            if city in prompt:
                normalized = city.replace("פתח תקוה", "פתח תקווה").replace("קריית אונו", "קרית אונו")
                found.append(normalized)

        found = list(dict.fromkeys(found))

        if found:
            filters.city_texts = found
            filters.city_text = found[0] if len(found) == 1 else None

        # מחיר
        m = re.search(r"מ[\s-]*(\d{3,6})\s*עד\s*(\d{3,6})", prompt)
        if m:
            filters.minPrice = int(m.group(1))
            filters.maxPrice = int(m.group(2))

        if filters.maxPrice is None:
            m = re.search(r"עד\s*(\d{3,6})", prompt)
            if m:
                filters.maxPrice = int(m.group(1))

        # חדרים
        m = re.search(r"בין\s*(\d+(?:\.\d+)?)\s*ל[\s-]*(\d+(?:\.\d+)?)\s*חדר", prompt)
        if m:
            filters.minRooms = float(m.group(1))
            filters.maxRooms = float(m.group(2))

        filters.must_have = filters.must_have or []
        filters.exclude = filters.exclude or []

        if any(x in prompt for x in ["ממד", "ממ״ד", 'ממ"ד']):
            if "mamad" not in filters.must_have:
                filters.must_have.append("mamad")

        if "מעלית" in prompt:
            if "elevator" not in filters.must_have:
                filters.must_have.append("elevator")

        if "חניה" in prompt:
            if "parking" not in filters.must_have:
                filters.must_have.append("parking")

        if "לא קרקע" in prompt or "לא קומת קרקע" in prompt:
            if "ground_floor" not in filters.exclude:
                filters.exclude.append("ground_floor")

        return filters

    def _apply_known_city_mapping(self, filters: SearchFilters) -> None:
        city_map = {
            "הרצליה": {
                "multiCity": "0417",
                "multiArea": "18",
                "multiNeighborhood": "413",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "פתח תקווה": {
                "multiArea": "18",
                "bBox": "32.077494,34.791048,32.294470,34.872168",
            },
            "קרית אונו": {
                "multiArea": "18",
                "bBox": "32.015000,34.770000,32.120000,34.900000",
            },
            "רעננה": {
                "multiArea": "18",
                "bBox": "32.140000,34.780000,32.240000,34.920000",
            },
            "כפר סבא": {
                "multiArea": "18",
                "bBox": "32.130000,34.780000,32.250000,34.980000",
            },
            "נתניה": {
                "multiArea": "78",
                "bBox": "32.230000,34.780000,32.360000,34.900000",
            },
        }

        cities = filters.city_texts or []

        if filters.city_text and filters.city_text not in cities:
            cities.append(filters.city_text)

        if not cities:
            return

        mapped = [c for c in cities if c in city_map]

        if len(mapped) == 1:
            for k, v in city_map[mapped[0]].items():
                setattr(filters, k, v)
        else:
            filters.multiNeighborhood = None
            filters.multiCity = None
            filters.multiArea = "18"
            filters.bBox = "32.015000,34.770000,32.300000,34.980000"

    def _apply_default_map_scope(self, filters: SearchFilters) -> None:
        filters.region = filters.region or 1
        filters.imageOnly = 1
        filters.priceOnly = 1
        filters.zoom = filters.zoom or 11

        if not filters.bBox:
            filters.bBox = "32.077494,34.791048,32.294470,34.872168"