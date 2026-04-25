from pydantic import BaseModel, Field


class Apartment(BaseModel):
    order_id: int | None = None
    token: str | None = None

    price: int | None = None
    rooms: float | None = None
    square_meter: float | None = None

    property_type: str | None = None
    description: str | None = None

    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    house_number: int | None = None
    floor: int | None = None

    lat: float | None = None
    lon: float | None = None

    cover_image: str | None = None
    images: list[str] = Field(default_factory=list)

    yad2_url: str | None = None