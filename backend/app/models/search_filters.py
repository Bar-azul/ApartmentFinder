from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    region: int | None = 1
    city: str | None = None
    area: str | None = None

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
    city_texts: list[str] = Field(default_factory=list)

    must_have: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    raw_prompt: str | None = None


class PromptSearchRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    must_have: list[str] = Field(default_factory=list)


class DirectSearchRequest(BaseModel):
    filters: SearchFilters