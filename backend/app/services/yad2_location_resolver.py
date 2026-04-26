from __future__ import annotations

from dataclasses import dataclass

from app.models.search_filters import SearchFilters


@dataclass(frozen=True)
class Yad2CityLocation:
    city_name: str
    city_id: str
    area_id: str
    bBox: str
    zoom: int = 13
    region_id: int = 1


class Yad2LocationResolver:
    CITY_INDEX: dict[str, Yad2CityLocation] = {
        "ראש העין": Yad2CityLocation(
            city_name="ראש העין",
            city_id="2640",
            area_id="71",
            bBox="32.070892,34.950645,32.117557,34.975878",
            zoom=13,
        ),
        "אילת": Yad2CityLocation(
            city_name="אילת",
            city_id="2600",
            area_id="24",
            bBox="29.490000,34.880000,29.620000,35.020000",
            zoom=13,
        ),
        "ראשון לציון": Yad2CityLocation(
            city_name="ראשון לציון",
            city_id="8300",
            area_id="2",
            bBox="31.940000,34.720000,31.995000,34.850000",
            zoom=13,
        ),
        "תל אביב": Yad2CityLocation(
            city_name="תל אביב",
            city_id="5000",
            area_id="2",
            bBox="32.020000,34.730000,32.140000,34.850000",
            zoom=13,
        ),
        "הרצליה": Yad2CityLocation(
            city_name="הרצליה",
            city_id="0417",
            area_id="18",
            bBox="32.077494,34.791048,32.294470,34.872168",
            zoom=12,
        ),
        "פתח תקווה": Yad2CityLocation(
            city_name="פתח תקווה",
            city_id="7900",
            area_id="4",
            bBox="32.050000,34.830000,32.120000,34.930000",
            zoom=13,
        ),
        "רמת גן": Yad2CityLocation(
            city_name="רמת גן",
            city_id="8600",
            area_id="2",
            bBox="32.050000,34.790000,32.100000,34.850000",
            zoom=13,
        ),
        "חולון": Yad2CityLocation(
            city_name="חולון",
            city_id="6600",
            area_id="2",
            bBox="32.000000,34.730000,32.040000,34.810000",
            zoom=13,
        ),
        "בת ים": Yad2CityLocation(
            city_name="בת ים",
            city_id="6200",
            area_id="2",
            bBox="32.000000,34.720000,32.040000,34.770000",
            zoom=13,
        ),
    }

    def apply_location_filters(self, filters: SearchFilters) -> SearchFilters:
        cities = list(filters.city_texts or [])

        if filters.city_text and filters.city_text not in cities:
            cities.append(filters.city_text)

        if len(cities) != 1:
            return filters

        city_name = self._normalize_city_name(cities[0])
        location = self.CITY_INDEX.get(city_name)

        if not location:
            return filters

        filters.city_text = location.city_name
        filters.city_texts = [location.city_name]

        filters.region = location.region_id

        # יד2 Map API עובד טוב יותר עם city/area ולא multiCity/multiArea
        filters.multiCity = None
        filters.multiArea = None
        filters.multiNeighborhood = None

        setattr(filters, "city", location.city_id)
        setattr(filters, "area", location.area_id)

        filters.bBox = location.bBox
        filters.zoom = location.zoom

        return filters

    def _normalize_city_name(self, city: str) -> str:
        city = (city or "").strip()
        city = city.replace("פתח תקוה", "פתח תקווה")
        city = city.replace("תל-אביב", "תל אביב")
        city = city.replace("ראשלצ", "ראשון לציון")
        city = city.replace("ראשל״צ", "ראשון לציון")
        city = city.replace('ראשל"צ', "ראשון לציון")
        city = city.replace("קריית אונו", "קרית אונו")
        city = city.replace("זיכרון יעקב", "זכרון יעקב")
        return city