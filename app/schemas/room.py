from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.booking import validate_stay
from app.schemas.common import Money, PageParams


class RoomCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    number: str = Field(min_length=1, max_length=20, examples=["101"])
    room_type: str = Field(min_length=1, max_length=50, examples=["Deluxe"])
    description: str | None = Field(default=None, max_length=1000)
    capacity: int = Field(ge=1, le=20)
    price_per_night: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class RoomUpdate(BaseModel):
    """Partial update: only the fields sent by the client are changed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    number: str | None = Field(default=None, min_length=1, max_length=20)
    room_type: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=1000)
    capacity: int | None = Field(default=None, ge=1, le=20)
    price_per_night: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)

    @model_validator(mode="after")
    def required_fields_not_null(self) -> Self:
        # description may be cleared with null; the other columns are NOT NULL
        for name in ("number", "room_type", "capacity", "price_per_night"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    room_type: str
    description: str | None
    capacity: int
    price_per_night: Money
    created_at: datetime
    updated_at: datetime


class RoomFilter(PageParams):
    """Query params for GET /rooms."""

    min_capacity: int | None = Field(default=None, ge=1, description="Room fits at least N guests")
    max_capacity: int | None = Field(default=None, ge=1)
    min_price: Decimal | None = Field(default=None, ge=0, description="Min price per night")
    max_price: Decimal | None = Field(default=None, ge=0, description="Max price per night")

    @model_validator(mode="after")
    def ranges_are_valid(self) -> Self:
        if self.min_capacity and self.max_capacity and self.min_capacity > self.max_capacity:
            raise ValueError("min_capacity cannot be greater than max_capacity")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price cannot be greater than max_price")
        return self


class AvailabilityQuery(PageParams):
    """Query params for GET /rooms/available."""

    check_in: date
    check_out: date
    guests: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def stay_is_valid(self) -> Self:
        validate_stay(self.check_in, self.check_out)
        return self
