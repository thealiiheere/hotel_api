from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core import clock
from app.models.booking import BookingStatus
from app.schemas.common import Money, PageParams

MAX_NIGHTS = 365


def validate_stay(check_in: date, check_out: date) -> None:
    """Shared date rules for booking and availability search (raises ValueError -> 422)."""
    if check_in < clock.today():
        raise ValueError("check_in cannot be in the past")
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    if (check_out - check_in).days > MAX_NIGHTS:
        raise ValueError(f"a booking cannot be longer than {MAX_NIGHTS} nights")


class BookingCreate(BaseModel):
    # user_id is NOT accepted from the client: the owner is always the token's user
    room_id: int = Field(gt=0)
    check_in: date = Field(examples=["2026-11-10"])
    check_out: date = Field(examples=["2026-11-12"])
    guests: int = Field(ge=1, examples=[2])

    @model_validator(mode="after")
    def stay_is_valid(self) -> Self:
        validate_stay(self.check_in, self.check_out)
        return self


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    room_id: int
    check_in: date
    check_out: date
    guests: int
    nights: int
    nightly_rate: Money
    total_price: Money
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None


class MyBookingsFilter(PageParams):
    """Query params for GET /bookings/me."""

    status: BookingStatus | None = None


class BookingFilter(PageParams):
    """Query params for the admin list GET /bookings."""

    room_id: int | None = Field(default=None, gt=0)
    date_from: date | None = Field(default=None, description="Stays that end after this date")
    date_to: date | None = Field(default=None, description="Stays that start before this date")
    status: BookingStatus | None = None

    @model_validator(mode="after")
    def range_is_valid(self) -> Self:
        if self.date_from and self.date_to and self.date_from >= self.date_to:
            raise ValueError("date_from must be before date_to")
        return self
