from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.config import settings
from app.models.apartment import Apartment, ApartmentFeatures


class PlaywrightDetailsService:
    def __init__(self) -> None:
        self.browser_dir = Path("app/browser")
        self.browser_dir.mkdir(parents=True, exist_ok=True)

        self.state_file = self.browser_dir / "yad2_storage_state.json"

        self.headless = settings.playwright_headless
        self.slow_mo = 0 if self.headless else 80

        self.user_playwright: Playwright | None = None
        self.user_browser: Browser | None = None
        self.user_context: BrowserContext | None = None

        self.cache: dict[str, Apartment] = {}

    async def open_apartment_page(self, apartment: Apartment) -> None:
        if not apartment.token and not apartment.yad2_url:
            return

        url = self._build_url(apartment)

        try:
            context = await self._ensure_user_context()
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await page.bring_to_front()
            await page.wait_for_timeout(2_000)

            await self._save_state(context)

            print("Yad2 listing opened in browser tab.")

        except Exception as e:
            print(f"Failed to open Yad2 listing: {e}")
            await self._reset_user_browser()

    async def _ensure_user_context(self) -> BrowserContext:
        if self.user_context:
            try:
                test_page = await self.user_context.new_page()
                await test_page.close()
                return self.user_context
            except Exception:
                await self._reset_user_browser()

        self.user_playwright = await async_playwright().start()

        self.user_browser = await self.user_playwright.chromium.launch(
            headless=False,
            slow_mo=80,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context_kwargs: dict[str, Any] = {
            "locale": "he-IL",
            "timezone_id": "Asia/Jerusalem",
            "viewport": {"width": 1400, "height": 900},
        }

        if self.state_file.exists():
            context_kwargs["storage_state"] = str(self.state_file)

        self.user_context = await self.user_browser.new_context(**context_kwargs)

        return self.user_context

    async def _reset_user_browser(self) -> None:
        try:
            if self.user_context:
                await self.user_context.close()
        except Exception:
            pass

        try:
            if self.user_browser:
                await self.user_browser.close()
        except Exception:
            pass

        try:
            if self.user_playwright:
                await self.user_playwright.stop()
        except Exception:
            pass

        self.user_context = None
        self.user_browser = None
        self.user_playwright = None

    async def enrich_many(
            self,
            apartments: list[Apartment],
            must_have: list[str] | None = None,
    ) -> list[Apartment]:
        if not apartments:
            return []

        must_have = must_have or []

        max_items = max(1, settings.playwright_max_details_per_search)
        concurrency = max(1, settings.playwright_detail_concurrency)
        batch_size = max(1, settings.playwright_batch_size)
        batch_delay = max(0, settings.playwright_batch_delay_seconds)

        limited = apartments[:max_items]
        untouched = apartments[max_items:]

        playwright = await async_playwright().start()
        browser: Browser | None = None
        context: BrowserContext | None = None

        try:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            context_kwargs: dict[str, Any] = {
                "locale": "he-IL",
                "timezone_id": "Asia/Jerusalem",
                "viewport": {"width": 1400, "height": 900},
            }

            if self.state_file.exists():
                context_kwargs["storage_state"] = str(self.state_file)

            context = await browser.new_context(**context_kwargs)

            all_enriched: list[Apartment] = []

            for start in range(0, len(limited), batch_size):
                batch = limited[start: start + batch_size]
                batch_number = (start // batch_size) + 1

                print(
                    f"Enriching batch {batch_number}: "
                    f"{len(batch)} apartments, concurrency={concurrency}"
                )

                semaphore = asyncio.Semaphore(concurrency)

                async def run(apartment: Apartment) -> Apartment:
                    async with semaphore:
                        return await self._enrich_with_context(context, apartment)

                enriched_items = await asyncio.gather(
                    *(run(apartment) for apartment in batch),
                    return_exceptions=True,
                )

                for index, item in enumerate(enriched_items):
                    if isinstance(item, Exception):
                        print(f"Failed to enrich apartment: {item}")
                        all_enriched.append(batch[index])
                    else:
                        all_enriched.append(item)

                await self._save_state(context)

                if start + batch_size < len(limited) and batch_delay > 0:
                    await asyncio.sleep(batch_delay)

            all_enriched.extend(untouched)

            if must_have:
                all_enriched = [
                    apartment
                    for apartment in all_enriched
                    if self._matches_must_have(apartment, must_have)
                ]

            return all_enriched

        finally:
            try:
                if context:
                    await context.close()
            except Exception:
                pass

            try:
                if browser:
                    await browser.close()
            except Exception:
                pass

            try:
                await playwright.stop()
            except Exception:
                pass

    async def enrich_apartment(self, apartment: Apartment) -> Apartment:
        enriched = await self.enrich_many([apartment])
        return enriched[0] if enriched else apartment

    async def _enrich_with_context(
        self,
        context: BrowserContext,
        apartment: Apartment,
    ) -> Apartment:
        if not apartment.token:
            return apartment

        if apartment.token in self.cache:
            return self.cache[apartment.token]

        page = None

        try:
            page = await context.new_page()
            await page.goto(self._build_url(apartment), wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3_000)

            html_text = await page.content()
            page_text = await page.inner_text("body")

            if self._is_captcha(html_text, page_text):
                print(f"CAPTCHA detected on token={apartment.token}. Skipping enrichment.")
                return apartment

            item_data = self._extract_next_data(html_text, apartment.token)

            if item_data:
                apartment = self._merge_details(apartment, item_data)
            else:
                description = self._extract_description_from_page_text(page_text)
                meta_description = self._extract_meta_description(html_text)

                apartment.description = description or meta_description or apartment.description
                apartment.search_text = page_text
                apartment.features = self._features_from_text(page_text)

            self.cache[apartment.token] = apartment
            return apartment

        except Exception as e:
            print(f"Failed to enrich apartment token={apartment.token}: {e}")
            return apartment

        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    async def _save_state(self, context: BrowserContext) -> None:
        try:
            await context.storage_state(path=str(self.state_file))
        except Exception:
            pass

    def _is_captcha(self, html_text: str, page_text: str = "") -> bool:
        combined = f"{html_text or ''}\n{page_text or ''}".lower()

        legit_indicators = [
            "הצג מספר טלפון",
            "שליחת הודעה",
            "חדרים",
            "מ״ר",
            "מקל בניין",
        ]

        if any(x in combined for x in legit_indicators):
            return False

        captcha_indicators = [
            "shieldsquare captcha",
            "validate.perfdrive.com",
            "why am i seeing this page",
        ]

        return any(x in combined for x in captcha_indicators)

    def _build_url(self, apartment: Apartment) -> str:
        return apartment.yad2_url or f"https://www.yad2.co.il/realestate/item/{apartment.token}"

    def _matches_must_have(self, apartment: Apartment, must_have: list[str]) -> bool:
        features = apartment.features

        for item in must_have:
            if item == "mamad" and not features.mamad:
                return False
            if item == "elevator" and not features.elevator:
                return False
            if item == "parking" and not features.parking:
                return False

        return True

    def _extract_next_data(self, html_text: str, token: str) -> dict[str, Any] | None:
        soup = BeautifulSoup(html_text, "html.parser")
        script = soup.find("script", {"id": "__NEXT_DATA__"})

        if not script or not script.string:
            return None

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return None

        return self._find_item(data, token)

    def _find_item(self, obj: Any, token: str) -> dict[str, Any] | None:
        if isinstance(obj, dict):
            if obj.get("token") == token and (
                "address" in obj
                or "metaData" in obj
                or "inProperty" in obj
                or "additionalDetails" in obj
                or "searchText" in obj
            ):
                return obj

            for value in obj.values():
                found = self._find_item(value, token)
                if found:
                    return found

        if isinstance(obj, list):
            for item in obj:
                found = self._find_item(item, token)
                if found:
                    return found

        return None

    def _extract_meta_description(self, html_text: str) -> str | None:
        soup = BeautifulSoup(html_text, "html.parser")

        tag = soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            return tag["content"].strip()

        tag = soup.find("meta", attrs={"property": "og:description"})
        if tag and tag.get("content"):
            return tag["content"].strip()

        return None

    def _extract_description_from_page_text(self, page_text: str) -> str | None:
        if not page_text:
            return None

        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        joined = "\n".join(lines)

        markers = ["תיאור הנכס", "תיאור", "על הנכס"]
        stop_markers = [
            "פרטים נוספים",
            "מה יש בנכס",
            "מיקום",
            "היסטוריית מחירים",
            "מודעות נוספות",
            "הצג מספר טלפון",
        ]

        for marker in markers:
            if marker in joined:
                after = joined.split(marker, 1)[1].strip()

                for stop in stop_markers:
                    if stop in after:
                        after = after.split(stop, 1)[0].strip()

                cleaned = "\n".join(line.strip() for line in after.splitlines() if line.strip())

                if len(cleaned) >= 20:
                    return cleaned[:1200]

        candidates = [
            line
            for line in lines
            if len(line) > 35
            and "₪" not in line
            and "חדרים" not in line
            and "מ״ר" not in line
            and "הצג מספר" not in line
        ]

        return candidates[0] if candidates else None

    def _merge_details(self, apartment: Apartment, details: dict[str, Any]) -> Apartment:
        metadata = details.get("metaData") or {}
        in_property = details.get("inProperty") or {}
        additional = details.get("additionalDetails") or {}

        apartment.description = (
            metadata.get("description")
            or details.get("description")
            or details.get("searchText")
            or apartment.description
        )

        apartment.search_text = details.get("searchText") or apartment.search_text

        if metadata.get("images"):
            apartment.images = metadata.get("images")

        if metadata.get("coverImage"):
            apartment.cover_image = metadata.get("coverImage")

        if additional.get("roomsCount"):
            apartment.rooms = additional.get("roomsCount")

        if additional.get("squareMeter"):
            apartment.square_meter = additional.get("squareMeter")

        apartment.features = self._normalize_features(
            in_property=in_property,
            text=f"{apartment.description or ''} {apartment.search_text or ''}",
        )

        return apartment

    def _normalize_features(
        self,
        in_property: dict[str, Any],
        text: str,
    ) -> ApartmentFeatures:
        return ApartmentFeatures(
            elevator=bool(in_property.get("includeElevator")) or self._has(text, ["מעלית"]),
            parking=bool(in_property.get("includeParking")) or self._has(text, ["חניה", "חנייה", "חניה פרטית"]),
            mamad=bool(in_property.get("includeSecurityRoom")) or self._has(text, ["ממד", "ממ״ד", 'ממ"ד']),
            air_conditioner=bool(in_property.get("includeAirconditioner")) or self._has(text, ["מיזוג", "מזגן", "מזגנים"]),
            balcony=bool(in_property.get("includeBalcony")) or self._has(text, ["מרפסת", "בלקון"]),
            furniture=bool(in_property.get("includeFurniture")) or self._has(text, ["ריהוט", "מרוהטת", "מרוהט"]),
            renovated=bool(in_property.get("isRenovated")) or self._has(text, ["משופץ", "משופצת", "שופצה"]),
            pets_allowed=bool(in_property.get("isPetsAllowed")) or self._has(text, ["בעלי חיים", "חיות מחמד"]),
            immediate_entrance=bool(in_property.get("isImmediateEntrance")) or self._has(text, ["כניסה מיידית", "כניסה מידית"]),
            building_shelter=bool(in_property.get("includeBuildingShelter")) or self._has(text, ["מקלט"]),
        )

    def _features_from_text(self, text: str) -> ApartmentFeatures:
        return self._normalize_features({}, text)

    def _has(self, text: str, words: list[str]) -> bool:
        normalized = (text or "").lower()
        normalized = normalized.replace("״", '"').replace("׳", "'")

        return any(
            word.lower().replace("״", '"').replace("׳", "'") in normalized
            for word in words
        )