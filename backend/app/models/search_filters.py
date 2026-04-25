from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    region: int | None = 1
    multiNeighborhood: str | None = None
    multiCity: str | None = None
    multiArea: str | None = None

    minPrice: int | None = None
    maxPrice: int | None = None

    minRooms: float | None = None
    maxRooms: float | None = None

    imageOnly: int | None = 1
    priceOnly: int | None = 1

    bBox: str | None = None
    zoom: int | None = 11

    city_text: str | None = None
    city_texts: list[str] = []

    must_have: list[str] = []
    exclude: list[str] = []

    raw_prompt: str | None = None


class PromptSearchRequest(BaseModel):
    prompt: str = Field(..., min_length=2)


class DirectSearchRequest(BaseModel):
    filters: SearchFilters