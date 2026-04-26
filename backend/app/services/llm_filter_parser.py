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

    def parse(self, prompt: str, selected_must_have: list[str] | None = None) -> SearchFilters:
        if not self.client:
            filters = self._fallback_parse(prompt)
        else:
            filters = self._parse_with_llm(prompt)

        filters.raw_prompt = prompt
        filters = self._post_process_prompt_rules(filters, prompt)
        self._merge_selected_must_have(filters, selected_must_have)
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
- אם יש עיר אחת: city_text וגם city_texts.
- אם יש כמה ערים: city_text=null ו-city_texts עם כולן.
- חשוב במיוחד לזהות ערים מרובות מילים: ראש העין, ראשון לציון, תל אביב, זכרון יעקב, כפר סבא, פתח תקווה.

must_have אפשריים:
- ממד / ממ״ד / ממ"ד => mamad
- מעלית => elevator
- חניה / חנייה => parking
- בעלי חיים / חיות מחמד / כלב / חתול => pets_allowed
- מרפסת / בלקון => balcony
- ריהוט / מרוהט / מרוהטת / רהיטים => furniture
- מיזוג / מזגן / מזגנים => air_conditioner
- משופצת / משופץ => renovated
- כניסה מיידית / כניסה מידית => immediate_entrance
- מקלט => building_shelter

exclude:
- לא קרקע / לא קומת קרקע => ground_floor
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
        return SearchFilters(raw_prompt=prompt)

    def _post_process_prompt_rules(self, filters: SearchFilters, prompt: str) -> SearchFilters:
        filters.must_have = filters.must_have or []
        filters.exclude = filters.exclude or []

        self._normalize_city_fields(filters)
        self._extract_city_from_prompt_generic(filters, prompt)

        self._normalize_city_fields(filters)
        self._apply_price_rules(filters, prompt)
        self._apply_room_rules(filters, prompt)
        self._apply_feature_rules(filters, prompt)
        self._apply_exclude_rules(filters, prompt)
        self._normalize_must_have(filters)

        return filters

    def _merge_selected_must_have(
        self,
        filters: SearchFilters,
        selected_must_have: list[str] | None,
    ) -> None:
        filters.must_have = filters.must_have or []

        if selected_must_have:
            for feature in selected_must_have:
                if feature and feature not in filters.must_have:
                    filters.must_have.append(feature)

        self._normalize_must_have(filters)

    def _normalize_must_have(self, filters: SearchFilters) -> None:
        allowed = {
            "mamad",
            "elevator",
            "parking",
            "pets_allowed",
            "balcony",
            "furniture",
            "air_conditioner",
            "renovated",
            "immediate_entrance",
            "building_shelter",
        }

        normalized = []

        for item in filters.must_have or []:
            if item in allowed and item not in normalized:
                normalized.append(item)

        filters.must_have = normalized

    def _normalize_city_fields(self, filters: SearchFilters) -> None:
        cities = filters.city_texts or []

        if filters.city_text and filters.city_text not in cities:
            cities.append(filters.city_text)

        normalized: list[str] = []

        for city in cities:
            clean = self._clean_city_candidate(city)
            if clean:
                normalized.append(clean)

        normalized = list(dict.fromkeys(normalized))

        filters.city_texts = normalized
        filters.city_text = normalized[0] if len(normalized) == 1 else None

    def _extract_city_from_prompt_generic(self, filters: SearchFilters, prompt: str) -> None:
        text = prompt.strip()

        known_multi_word_cities = [
            "ראש העין",
            "ראשון לציון",
            "תל אביב",
            "פתח תקווה",
            "פתח תקוה",
            "קרית אונו",
            "קריית אונו",
            "כפר סבא",
            "רמת גן",
            "אילת",
            "רמת השרון",
            "בני ברק",
            "נס ציונה",
            "זכרון יעקב",
            "זיכרון יעקב",
            "מזכרת בתיה",
            "הוד השרון",
            "אור יהודה",
            "בית שמש",
            "בית שאן",
            "בית דגן",
            "גני תקווה",
            "גני תקוה",
            "קרית גת",
            "קריית גת",
            "קרית מלאכי",
            "קריית מלאכי",
            "קרית שמונה",
            "קריית שמונה",
        ]

        found: list[str] = []

        for city in known_multi_word_cities:
            if city in text:
                normalized = self._clean_city_candidate(city)
                if normalized:
                    found.append(normalized)

        patterns = [
            r"(?:דירה|דירות|בית|בתים)\s+ב(.+?)(?:\s+עם|\s+בלי|\s+מ-|\s+עד|\s+בין|\s+\d|$)",
            r"(?:חפש לי|תמצא לי|מצא לי|מחפש)\s+(?:דירה|דירות|בית|בתים)?\s*ב(.+?)(?:\s+עם|\s+בלי|\s+מ-|\s+עד|\s+בין|\s+\d|$)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text):
                chunk = match.group(1).strip()
                parts = re.split(r"[,،/]|(?:\s+או\s+)", chunk)

                for part in parts:
                    city = self._clean_city_candidate(part)
                    if city:
                        found.append(city)

        existing = filters.city_texts or []
        cleaned_existing: list[str] = []

        for city in existing:
            if any(city != full_city and city in full_city for full_city in found):
                continue

            cleaned_existing.append(city)

        merged = cleaned_existing + found
        merged = list(dict.fromkeys(merged))

        filters.city_texts = merged
        filters.city_text = merged[0] if len(merged) == 1 else None

    def _clean_city_candidate(self, value: str) -> str | None:
        if not value:
            return None

        city = value.strip(" ,.-")
        city = re.sub(r"\s+", " ", city)

        city = city.replace("זיכרון יעקב", "זכרון יעקב")
        city = city.replace("פתח תקוה", "פתח תקווה")
        city = city.replace("קריית אונו", "קרית אונו")
        city = city.replace("תל-אביב", "תל אביב")
        city = city.replace("ראשלצ", "ראשון לציון")
        city = city.replace("ראשל״צ", "ראשון לציון")
        city = city.replace('ראשל"צ', "ראשון לציון")
        city = city.replace("גני תקוה", "גני תקווה")
        city = city.replace("קריית גת", "קרית גת")
        city = city.replace("קריית מלאכי", "קרית מלאכי")
        city = city.replace("קריית שמונה", "קרית שמונה")

        stop_words = {
            "חפש",
            "תמצא",
            "מצא",
            "לי",
            "דירה",
            "דירות",
            "בית",
            "בתים",
            "להשכרה",
            "השכרה",
            "עם",
            "בלי",
            "עד",
            "בין",
            "מ",
            "שקל",
            "חדר",
            "חדרים",
            "ממד",
            "ממ״ד",
            'ממ"ד',
            "מעלית",
            "חניה",
            "חנייה",
            "מרפסת",
            "ריהוט",
            "בעלי",
            "חיים",
        }

        words = [word for word in city.split() if word not in stop_words]
        city = " ".join(words).strip()

        if len(city) < 2:
            return None

        if re.search(r"\d", city):
            return None

        return city

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
        normalized_prompt = prompt.replace("–", "-").replace("—", "-")

        # דוגמאות:
        # בין 2 ל-4 חדרים
        # בין 2.5 ל-4 חדרים
        m = re.search(
            r"בין\s*(\d+(?:\.\d+)?)\s*ל[\s-]*(\d+(?:\.\d+)?)\s*חדר",
            normalized_prompt,
        )

        # דוגמאות:
        # 2-4 חדרים
        # 2 - 4 חדרים
        # 2.5-4 חדרים
        if not m:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*חדרים?",
                normalized_prompt,
            )

        # דוגמאות:
        # 2 עד 4 חדרים
        # 2.5 עד 4 חדרים
        if not m:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*עד\s*(\d+(?:\.\d+)?)\s*חדרים?",
                normalized_prompt,
            )

        if m:
            filters.minRooms = float(m.group(1))
            filters.maxRooms = float(m.group(2))
            return

        # דוגמאות:
        # 3 חדרים ומעלה
        # 2.5 חדרים ומעלה
        if filters.minRooms is None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*חדרים?\s*ומעלה", normalized_prompt)
            if m:
                filters.minRooms = float(m.group(1))

        # דוגמאות:
        # עד 4 חדרים
        # עד 3.5 חדרים
        if filters.maxRooms is None:
            m = re.search(r"עד\s*(\d+(?:\.\d+)?)\s*חדרים?", normalized_prompt)
            if m:
                filters.maxRooms = float(m.group(1))

        # דוגמה:
        # דירת 3 חדרים
        # במקרה כזה נשים גם מינימום וגם מקסימום 3
        if filters.minRooms is None and filters.maxRooms is None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*חדרים?", normalized_prompt)
            if m:
                rooms = float(m.group(1))
                filters.minRooms = rooms
                filters.maxRooms = rooms

    def _apply_feature_rules(self, filters: SearchFilters, prompt: str) -> None:
        feature_rules = {
            "mamad": ["ממד", "ממ״ד", 'ממ"ד'],
            "elevator": ["מעלית"],
            "parking": ["חניה", "חנייה", "חניה פרטית"],
            "pets_allowed": [
                "בעלי חיים",
                "חיות מחמד",
                "חיית מחמד",
                "כלב",
                "חתול",
                "עם בעלי חיים",
                "מאפשר בעלי חיים",
                "מתאים לבעלי חיים",
            ],
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

        if not filters.bBox:
            filters.bBox = "31.930000,34.650000,32.350000,35.000000"

        filters.multiNeighborhood = None
        filters.multiCity = None
        filters.multiArea = filters.multiArea or "18"