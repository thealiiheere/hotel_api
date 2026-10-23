from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.room import Room
from app.models.user import User


class BookingStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("check_in < check_out", name="dates_order"),
        CheckConstraint("guests > 0", name="guests_positive"),
        CheckConstraint("nightly_rate > 0", name="nightly_rate_positive"),
        # total_price must always equal nights x the rate copied at booking time
        CheckConstraint(
            "total_price = nightly_rate * (check_out - check_in)", name="total_price_matches"
        ),
        CheckConstraint("status IN ('active', 'cancelled')", name="status_valid"),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="cancelled_at_matches_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: a user or room with booking history cannot be deleted by accident
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    guests: Mapped[int]
    # Snapshot of the room price at booking time; later room price changes do not affect it
    nightly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(
        String(20), default=BookingStatus.ACTIVE, server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    room: Mapped[Room] = relationship()

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


# Database-level guarantee that active bookings of one room never overlap.
# daterange(check_in, check_out, '[)') is half-open, so a check-out day can be
# the next guest's check-in day. Cancelled bookings are excluded by the WHERE.
Booking.__table__.append_constraint(
    ExcludeConstraint(
        (Booking.__table__.c.room_id, "="),
        (func.daterange(Booking.__table__.c.check_in, Booking.__table__.c.check_out, "[)"), "&&"),
        name="ex_bookings_no_overlap",
        using="gist",
        where=text("status = 'active'"),
    )
)
