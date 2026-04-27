from pydantic import BaseModel, Field


class ApartmentFeatures(BaseModel):
    elevator: bool = False
    parking: bool = False
    mamad: bool = False
    air_conditioner: bool = False
    balcony: bool = False
    furniture: bool = False
    renovated: bool = False
    pets_allowed: bool = False
    immediate_entrance: bool = False
    building_shelter: bool = False


class Apartment(BaseModel):
    order_id: int | None = None
    ad_number: int | None = None
    token: str | None = None

    price: int | None = None
    rooms: float | None = None
    square_meter: float | None = None

    property_type: str | None = None
    description: str | None = None
    search_text: str | None = None

    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None
    house_number: int | None = None
    floor: int | None = None

    lat: float | None = None
    lon: float | None = None

    cover_image: str | None = None
    images: list[str] = Field(default_factory=list)

    features: ApartmentFeatures = Field(default_factory=ApartmentFeatures)

    # new
    verification_status: str = "not_required"
    # not_required / pending / checking / verified / rejected / failed

    verification_reason: str | None = None
    required_features: list[str] = Field(default_factory=list)

    yad2_url: str | None = None