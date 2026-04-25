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
            filters = self._fallback_parse(prompt)
        else:
            filters = self._parse_with_llm(prompt)

        filters.raw_prompt = prompt
        filters = self._post_process_prompt_rules(filters, prompt)
        self._apply_default_map_scope(filters)

        return filters

    def _parse_with_llm(self, prompt: str) -> SearchFilters:
        system_prompt = """
אתה ממיר בקשת חיפוש דירה בעברית ל-JSON בלבד.

החזר רק JSON תקין ללא markdown.

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

חוקים לערים:
- תזהה כל עיר/ישוב/מועצה שהמשתמש כתב.
- אל תמציא עיר.
- אם יש עיר אחת: החזר אותה גם ב-city_text וגם בתוך city_texts.
- אם יש כמה ערים: city_text=null ו-city_texts עם כולן.
- שמור את שם העיר בעברית בדיוק ככל האפשר.
- דוגמאות: ראשון לציון, תל אביב, רמת גן, גבעתיים, חולון, בת ים, הרצליה, רעננה, כפר סבא, פתח תקווה.

חוקים למחירים:
- "עד 5500" => maxPrice=5500
- "מ-4000 עד 5500" => minPrice=4000, maxPrice=5500
- "בין 4000 ל-5500" => minPrice=4000, maxPrice=5500

חוקים לחדרים:
- "בין 2.5 ל-4 חדרים" => minRooms=2.5, maxRooms=4
- "3 חדרים ומעלה" => minRooms=3
- "עד 4 חדרים" => maxRooms=4

must_have אפשריים בלבד:
- ממד / ממ״ד / ממ"ד => "mamad"
- מעלית => "elevator"
- חניה / חנייה => "parking"
- בעלי חיים / חיות מחמד / כלב / חתול / מאפשר בעלי חיים => "pets_allowed"
- מרפסת / בלקון => "balcony"
- ריהוט / מרוהט / מרוהטת / עם רהיטים => "furniture"
- מיזוג / מזגן / מזגנים => "air_conditioner"
- משופצת / משופץ => "renovated"
- כניסה מיידית / כניסה מידית => "immediate_entrance"
- מקלט => "building_shelter"

exclude אפשריים:
- לא קרקע / לא קומת קרקע => "ground_floor"

חשוב:
- אם המשתמש כותב "עם בעלי חיים" זה must_have=["pets_allowed"].
- אם המשתמש כותב "עם מרפסת" זה must_have=["balcony"].
- אם המשתמש כותב "עם ריהוט" זה must_have=["furniture"].
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
            return SearchFilters(**data)

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

        city_patterns = [
            r"בראשון לציון",
            r"ראשון לציון",
            r"בתל אביב",
            r"תל אביב",
            r"ברמת גן",
            r"רמת גן",
            r"בגבעתיים",
            r"גבעתיים",
            r"בחולון",
            r"חולון",
            r"בבת ים",
            r"בת ים",
            r"בהרצליה",
            r"הרצליה",
            r"בפתח תקווה",
            r"פתח תקווה",
            r"פתח תקוה",
            r"בקרית אונו",
            r"קרית אונו",
            r"קריית אונו",
            r"ברעננה",
            r"רעננה",
            r"בכפר סבא",
            r"כפר סבא",
            r"ברמת השרון",
            r"רמת השרון",
            r"בבני ברק",
            r"בני ברק",
            r"בנתניה",
            r"נתניה",
        ]

        found_cities: list[str] = []

        for pattern in city_patterns:
            if re.search(pattern, prompt):
                city = pattern.replace("ב", "", 1) if pattern.startswith("ב") else pattern
                city = city.replace("פתח תקוה", "פתח תקווה")
                city = city.replace("קריית אונו", "קרית אונו")
                found_cities.append(city)

        found_cities = list(dict.fromkeys(found_cities))

        if found_cities:
            filters.city_texts = found_cities
            filters.city_text = found_cities[0] if len(found_cities) == 1 else None

        return filters

    def _post_process_prompt_rules(self, filters: SearchFilters, prompt: str) -> SearchFilters:
        filters.must_have = filters.must_have or []
        filters.exclude = filters.exclude or []

        self._normalize_city_fields(filters)
        self._apply_price_rules(filters, prompt)
        self._apply_room_rules(filters, prompt)
        self._apply_feature_rules(filters, prompt)
        self._apply_exclude_rules(filters, prompt)

        return filters

    def _normalize_city_fields(self, filters: SearchFilters) -> None:
        cities = filters.city_texts or []

        if filters.city_text and filters.city_text not in cities:
            cities.append(filters.city_text)

        normalized = []

        for city in cities:
            if not city:
                continue

            clean = city.strip()
            clean = clean.replace("פתח תקוה", "פתח תקווה")
            clean = clean.replace("קריית אונו", "קרית אונו")
            clean = clean.replace("תל-אביב", "תל אביב")
            clean = clean.replace("ראשלצ", "ראשון לציון")
            clean = clean.replace("ראשל״צ", "ראשון לציון")
            clean = clean.replace('ראשל"צ', "ראשון לציון")

            normalized.append(clean)

        normalized = list(dict.fromkeys(normalized))

        filters.city_texts = normalized
        filters.city_text = normalized[0] if len(normalized) == 1 else None

    def _apply_price_rules(self, filters: SearchFilters, prompt: str) -> None:
        m = re.search(r"מ[\s-]*(\d{3,6})\s*עד\s*(\d{3,6})", prompt)
        if not m:
            m = re.search(r"בין\s*(\d{3,6})\s*ל[\s-]*(\d{3,6})", prompt)

        if m:
            filters.minPrice = int(m.group(1))
            filters.maxPrice = int(m.group(2))

        if filters.maxPrice is None:
            m = re.search(r"עד\s*(\d{3,6})", prompt)
            if m:
                filters.maxPrice = int(m.group(1))

        if filters.minPrice is None:
            m = re.search(r"מעל\s*(\d{3,6})", prompt)
            if m:
                filters.minPrice = int(m.group(1))

    def _apply_room_rules(self, filters: SearchFilters, prompt: str) -> None:
        m = re.search(r"בין\s*(\d+(?:\.\d+)?)\s*ל[\s-]*(\d+(?:\.\d+)?)\s*חדר", prompt)
        if m:
            filters.minRooms = float(m.group(1))
            filters.maxRooms = float(m.group(2))

        if filters.minRooms is None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*חדרים?\s*ומעלה", prompt)
            if m:
                filters.minRooms = float(m.group(1))

        if filters.maxRooms is None:
            m = re.search(r"עד\s*(\d+(?:\.\d+)?)\s*חדר", prompt)
            if m:
                filters.maxRooms = float(m.group(1))

    def _apply_feature_rules(self, filters: SearchFilters, prompt: str) -> None:
        feature_rules = {
            "mamad": ["ממד", "ממ״ד", 'ממ"ד'],
            "elevator": ["מעלית"],
            "parking": ["חניה", "חנייה", "חניה פרטית"],
            "pets_allowed": ["בעלי חיים", "חיות מחמד", "כלב", "חתול", "עם בעלי חיים", "מאפשר בעלי חיים"],
            "balcony": ["מרפסת", "בלקון"],
            "furniture": ["ריהוט", "מרוהט", "מרוהטת", "רהיטים", "עם רהיטים"],
            "air_conditioner": ["מיזוג", "מזגן", "מזגנים"],
            "renovated": ["משופץ", "משופצת", "שופצה"],
            "immediate_entrance": ["כניסה מיידית", "כניסה מידית"],
            "building_shelter": ["מקלט"],
        }

        for key, words in feature_rules.items():
            if any(word in prompt for word in words):
                if key not in filters.must_have:
                    filters.must_have.append(key)

    def _apply_exclude_rules(self, filters: SearchFilters, prompt: str) -> None:
        if "לא קרקע" in prompt or "לא קומת קרקע" in prompt:
            if "ground_floor" not in filters.exclude:
                filters.exclude.append("ground_floor")

    def _apply_default_map_scope(self, filters: SearchFilters) -> None:
        filters.region = filters.region or 1
        filters.imageOnly = 1
        filters.priceOnly = 1
        filters.zoom = filters.zoom or 11

        # ברירת מחדל רחבה יותר במרכז — כדי שגם ראשון לציון / תל אביב / חולון / רמת גן יתפסו
        if not filters.bBox:
            filters.bBox = "31.930000,34.650000,32.350000,35.000000"

        # לא עובדים יותר עם city_map ידני.
        # אם יש עיר אחת/כמה ערים, הסינון המדויק נעשה אחרי map api לפי apartment.city.
        filters.multiNeighborhood = None
        filters.multiCity = None
        filters.multiArea = filters.multiArea or "18"