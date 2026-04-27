from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.models.search_filters import SearchFilters

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Yad2CityLocation:
    city_name: str
    city_id: str
    area_id: str
    bBox: str
    zoom: int = 13
    region_id: int = 1


class Yad2LocationResolver:
    CACHE_FILE = Path("app/data/yad2_location_cache.json")
    RENT_URL = "https://www.yad2.co.il/realestate/rent"

    def get_requested_cities(self, filters: SearchFilters) -> list[str]:
        cities: list[str] = []

        for city in filters.city_texts or []:
            city = self._normalize_city_name(city)
            if city and city not in cities:
                cities.append(city)

        if filters.city_text:
            city = self._normalize_city_name(filters.city_text)
            if city and city not in cities:
                cities.append(city)

        return cities

    def resolve_city(self, city_name: str) -> Yad2CityLocation | None:
        city_name = self._normalize_city_name(city_name)
        return self._get_from_cache(city_name)

    async def resolve_city_async(self, city_name: str) -> Yad2CityLocation | None:
        city_name = self._normalize_city_name(city_name)

        location = self._get_from_cache(city_name)
        if location:
            return location

        location = await self._resolve_from_yad2(city_name)

        if location:
            self._save_to_cache(city_name, location)

        return location

    def apply_location_to_filters(
        self,
        filters: SearchFilters,
        location: Yad2CityLocation,
    ) -> SearchFilters:
        filters.city_text = location.city_name
        filters.city_texts = [location.city_name]

        filters.region = location.region_id
        filters.city = location.city_id
        filters.area = location.area_id
        filters.bBox = location.bBox
        filters.zoom = location.zoom

        filters.multiCity = None
        filters.multiArea = None
        filters.multiNeighborhood = None

        return filters

    async def apply_location_filters(self, filters: SearchFilters) -> SearchFilters:
        cities = self.get_requested_cities(filters)

        if len(cities) != 1:
            return filters

        location = await self.resolve_city_async(cities[0])

        if not location:
            logger.warning("Could not resolve city location for: %s", cities[0])
            return filters

        return self.apply_location_to_filters(filters, location)

    async def _resolve_from_yad2(self, city_name: str) -> Yad2CityLocation | None:
        print(f"YAD2 LOCATION RESOLVER: trying Playwright for city='{city_name}'")

        captured_location: Yad2CityLocation | None = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=80,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )

            context = await browser.new_context(
                locale="he-IL",
                timezone_id="Asia/Jerusalem",
                viewport={"width": 1400, "height": 900},
                ignore_https_errors=True,
                service_workers="block",
            )

            page = await context.new_page()

            async def block_wrong_yad1_routes(route):
                url = route.request.url

                if "/yad1/developers/" in url or "/yad1/project/" in url:
                    print(f"YAD2 LOCATION RESOLVER: blocked wrong yad1 navigation: {url}")
                    await route.abort()
                    return

                await route.continue_()

            await page.route("**/*", block_wrong_yad1_routes)

            async def on_request(request):
                nonlocal captured_location

                url = request.url

                if "realestate-feed/rent/map" not in url:
                    return

                location = self._try_location_from_url(city_name, url)
                if location:
                    print("YAD2 LOCATION RESOLVER captured map url:", url)
                    captured_location = location

            page.on("request", on_request)

            try:
                await self._goto_rent_page(page)

                await page.wait_for_timeout(2500)
                await self._close_popups(page)
                await self._ensure_rent_page(page)

                input_locator = await self._find_location_input_strict(page)

                if not input_locator:
                    print("YAD2 LOCATION RESOLVER: rent location input not found")
                    await self._debug_page_state(page)
                    return None

                if not await self._type_city_into_input(input_locator, city_name):
                    print("YAD2 LOCATION RESOLVER: city was not typed into input")
                    await self._debug_page_state(page)
                    return None

                await page.wait_for_timeout(1800)

                if not await self._select_city_suggestion_prefer_city(page, city_name):
                    print("YAD2 LOCATION RESOLVER: city suggestion was not selected")
                    await self._debug_page_state(page)
                    return None

                await page.wait_for_timeout(900)

                await self._submit_rent_search(page)

                await page.wait_for_timeout(8000)

                if captured_location:
                    print(f"YAD2 LOCATION RESOLVER: resolved {city_name} -> {captured_location}")
                    return captured_location

                current_location = self._try_location_from_url(city_name, page.url)
                if current_location:
                    print(f"YAD2 LOCATION RESOLVER: resolved from URL: {page.url}")
                    return current_location

                print(f"YAD2 LOCATION RESOLVER: no map request captured for {city_name}")
                await self._debug_page_state(page)
                return None

            except PlaywrightTimeoutError:
                logger.exception("Yad2 city resolver timeout for city: %s", city_name)
                return None

            except Exception as e:
                logger.exception("Yad2 city resolver failed for city=%s error=%s", city_name, e)
                return None

            finally:
                await context.close()
                await browser.close()

    async def _goto_rent_page(self, page) -> None:
        await page.goto(
            self.RENT_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )

        await page.wait_for_timeout(1200)

        if "/yad1" in page.url:
            print(f"YAD2 LOCATION RESOLVER: redirected to yad1 url={page.url}, forcing rent url")

            await page.goto(
                self.RENT_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            await page.wait_for_timeout(1200)

    async def _ensure_rent_page(self, page) -> None:
        for attempt in range(3):
            url = page.url

            if "/realestate/rent" in url and "/yad1" not in url:
                return

            print(f"YAD2 LOCATION RESOLVER: not on rent page attempt={attempt + 1}, url={url}")

            await page.goto(
                self.RENT_URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            await page.wait_for_timeout(1200)

    async def _find_location_input_strict(self, page):
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(500)

        selectors = [
            'input[placeholder*="חיפוש לפי אזור"]',
            'input[placeholder*="אזור, עיר"]',
            'input[placeholder*="עיר, שכונה"]',
            'input[placeholder*="עיר"]',
            'input[placeholder*="אזור"]',
            'input[placeholder*="שכונה"]',
            'input[placeholder*="רחוב"]',
            'input[type="text"]',
            'input[type="search"]',
        ]

        forbidden_words = [
            "חברה",
            "פרויקט",
            "יזם",
            "יזמים",
            "מיקום",
        ]

        best_locator = None
        best_score = -9999
        best_debug = None

        for selector in selectors:
            try:
                inputs = page.locator(selector)
                count = await inputs.count()

                for i in range(count):
                    locator = inputs.nth(i)

                    if not await locator.is_visible():
                        continue

                    box = await locator.bounding_box()
                    if not box:
                        continue

                    placeholder = await locator.get_attribute("placeholder") or ""
                    name = await locator.get_attribute("name") or ""
                    aria = await locator.get_attribute("aria-label") or ""

                    combined = f"{placeholder} {name} {aria}"

                    if any(word in combined for word in forbidden_words):
                        continue

                    if box["width"] < 120 or box["height"] < 15:
                        continue

                    score = 0

                    if 170 <= box["y"] <= 440:
                        score += 100

                    if "אזור" in combined:
                        score += 30

                    if "עיר" in combined:
                        score += 30

                    if "שכונה" in combined:
                        score += 15

                    if "רחוב" in combined:
                        score += 15

                    if "חיפוש לפי אזור" in combined:
                        score += 40

                    if box["y"] < 150:
                        score -= 100

                    if box["y"] > 520:
                        score -= 100

                    if score > best_score:
                        best_score = score
                        best_locator = locator
                        best_debug = {
                            "selector": selector,
                            "placeholder": placeholder,
                            "name": name,
                            "aria": aria,
                            "box": box,
                            "score": score,
                        }

            except Exception:
                continue

        if best_locator and best_score > 0:
            print(f"YAD2 LOCATION RESOLVER: selected input {best_debug}")

            await best_locator.scroll_into_view_if_needed(timeout=2000)
            await best_locator.click(timeout=2500, force=True)
            await page.wait_for_timeout(300)
            return best_locator

        return None

    async def _type_city_into_input(self, input_locator, city_name: str) -> bool:
        try:
            await input_locator.click(timeout=2500, force=True)
            await input_locator.fill("")
            await input_locator.type(city_name, delay=80)

            await input_locator.page.wait_for_timeout(700)

            value = await input_locator.input_value()
            print(f"YAD2 LOCATION RESOLVER: input value after typing='{value}'")

            return city_name in value

        except Exception as e:
            print(f"YAD2 LOCATION RESOLVER: failed typing city: {e}")
            return False

    async def _select_city_suggestion_prefer_city(self, page, city_name: str) -> bool:
        bad_words = [
            "פרויקט",
            "חדש",
            "יזם",
            "קבלן",
            "חברה",
            "יזמים",
            "₪",
            "חדרים",
            "מ״ר",
            "מומלץ",
            "גלריה",
        ]

        candidates: list[tuple[Any, str, dict, int]] = []

        try:
            locators = page.locator(
                "li, [role='option'], [role='listitem'], button, div, span"
            ).filter(has_text=city_name)

            count = await locators.count()

            for i in range(min(count, 120)):
                item = locators.nth(i)

                try:
                    if not await item.is_visible():
                        continue

                    box = await item.bounding_box()
                    if not box:
                        continue

                    if box["y"] < 240 or box["y"] > 620:
                        continue

                    text = (await item.inner_text()).strip()
                    lines = [line.strip() for line in text.splitlines() if line.strip()]

                    if city_name not in text:
                        continue

                    if any(word in text for word in bad_words):
                        continue

                    score = 0

                    if any(line == city_name for line in lines):
                        score += 100

                    if "עיר" in lines or text.startswith("עיר"):
                        score += 80

                    if "אזור" in lines or text.startswith("אזור"):
                        score -= 70

                    if "שכונה" in lines or text.startswith("שכונה"):
                        score -= 50

                    if "והסביבה" in text:
                        score -= 80

                    if score > 0:
                        candidates.append((item, text, box, score))

                except Exception:
                    continue

        except Exception:
            pass

        if not candidates:
            print("YAD2 LOCATION RESOLVER: no city suggestion candidates")
            return False

        candidates.sort(key=lambda x: x[3], reverse=True)

        item, text, box, score = candidates[0]

        await item.click(timeout=2500, force=True)

        print(
            "YAD2 LOCATION RESOLVER: clicked best city suggestion "
            f"score={score} text='{text}' box={box}"
        )

        return True

    async def _submit_rent_search(self, page) -> bool:
        try:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1800)
            print("YAD2 LOCATION RESOLVER: submitted with Enter")
            return True
        except Exception:
            pass

        try:
            buttons = page.get_by_role("button")
            count = await buttons.count()

            for i in range(count):
                button = buttons.nth(i)

                if not await button.is_visible():
                    continue

                box = await button.bounding_box()
                if not box:
                    continue

                if box["y"] < 210 or box["y"] > 460:
                    continue

                text = (await button.inner_text()).strip()
                aria = await button.get_attribute("aria-label") or ""

                if text not in {"חיפוש", "חפש"} and "חיפוש" not in aria and "search" not in aria.lower():
                    continue

                await button.click(timeout=2500, force=True)

                print(
                    "YAD2 LOCATION RESOLVER: clicked hero search button "
                    f"text='{text}' aria='{aria}' box={box}"
                )
                return True

        except Exception:
            pass

        return False

    async def _close_popups(self, page) -> None:
        for text in ["אישור", "הבנתי", "סגור", "לא תודה", "קבל", "אני מסכים"]:
            try:
                button = page.get_by_text(text, exact=False).first

                if await button.count():
                    box = await button.bounding_box()

                    if box and box["y"] < 600:
                        await button.click(timeout=1000)
                        await page.wait_for_timeout(400)

            except Exception:
                pass

    async def _debug_page_state(self, page) -> None:
        try:
            print("YAD2 LOCATION RESOLVER DEBUG URL:", page.url)

            inputs = await page.evaluate(
                """
                () => Array.from(document.querySelectorAll('input')).map((el, index) => {
                    const r = el.getBoundingClientRect();

                    return {
                        index,
                        type: el.type,
                        placeholder: el.placeholder,
                        value: el.value,
                        name: el.name,
                        ariaLabel: el.getAttribute('aria-label'),
                        visible: r.width > 0 && r.height > 0,
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height
                    };
                })
                """
            )

            print(
                "YAD2 LOCATION RESOLVER DEBUG INPUTS:",
                json.dumps(inputs, ensure_ascii=False, indent=2),
            )

        except Exception as e:
            print(f"YAD2 LOCATION RESOLVER DEBUG FAILED: {e}")

    def _try_location_from_url(self, city_name: str, url: str) -> Yad2CityLocation | None:
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            city_id = self._first(params, "city")
            area_id = self._first(params, "area")
            region_id = self._first(params, "region")
            bbox = self._first(params, "bBox")
            zoom = self._first(params, "zoom")

            if city_id and area_id and region_id and bbox:
                return Yad2CityLocation(
                    city_name=city_name,
                    city_id=city_id,
                    area_id=area_id,
                    region_id=int(region_id),
                    bBox=bbox,
                    zoom=int(zoom or 13),
                )

        except Exception:
            return None

        return None

    def _get_from_cache(self, city_name: str) -> Yad2CityLocation | None:
        cache = self._load_cache()
        item = cache.get(city_name)

        if not item:
            return None

        try:
            return Yad2CityLocation(**item)
        except Exception:
            return None

    def _save_to_cache(self, city_name: str, location: Yad2CityLocation) -> None:
        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

        cache = self._load_cache()
        cache[city_name] = asdict(location)

        self.CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"YAD2 LOCATION RESOLVER: saved city to cache: {city_name}")

    def _load_cache(self) -> dict:
        if not self.CACHE_FILE.exists():
            return {}

        try:
            return json.loads(self.CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _normalize_city_name(self, city: str) -> str:
        city = (city or "").strip()
        city = re.sub(r"\s+", " ", city)

        replacements = {
            "פתח תקוה": "פתח תקווה",
            "פתח-תקווה": "פתח תקווה",
            "פתח-תקוה": "פתח תקווה",
            "תל-אביב": "תל אביב",
            "תא": "תל אביב",
            "ת״א": "תל אביב",
            'ת"א': "תל אביב",
            "ראשלצ": "ראשון לציון",
            "ראשל״צ": "ראשון לציון",
            'ראשל"צ': "ראשון לציון",
            "קריית אונו": "קרית אונו",
            "קרית-אונו": "קרית אונו",
            "זיכרון יעקב": "זכרון יעקב",
            "בת-ים": "בת ים",
            "באר-שבע": "באר שבע",
            "בארשבע": "באר שבע",
            "באר שבעע": "באר שבע",
            "כפר-סבא": "כפר סבא",
            "הוד-השרון": "הוד השרון",
        }

        for old, new in replacements.items():
            city = city.replace(old, new)

        return city.strip()

    def _first(self, params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        return values[0] if values else None