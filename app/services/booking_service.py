"""Booking rules: price calculation, overlap protection, ownership and cancellation."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import clock
from app.core.exceptions import BusinessValidationError, ConflictError, NotFoundError
from app.db.pagination import paginate
from app.models.booking import Booking, BookingStatus
from app.models.room import Room
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingFilter, MyBookingsFilter
from app.services.room_service import overlapping_bookings

EXCLUSION_VIOLATION = "23P01"  # PostgreSQL SQLSTATE raised by ex_bookings_no_overlap


def create_booking(db: Session, user: User, data: BookingCreate) -> Booking:
    # 1) Lock the room row (SELECT ... FOR UPDATE). Parallel requests for the same
    #    room wait here and run one at a time, so check + insert below is atomic.
    room = db.scalar(select(Room).where(Room.id == data.room_id).with_for_update())
    if room is None:
        raise NotFoundError("Room not found")

    # 2) Guest count must fit the room
    if data.guests > room.capacity:
        raise BusinessValidationError(f"Room capacity is {room.capacity}, got {data.guests} guests")

    # 3) No overlap with another active booking of this room, period is [check_in, check_out)
    overlap = overlapping_bookings(room.id, data.check_in, data.check_out).limit(1)
    if db.scalar(overlap) is not None:
        raise ConflictError("Room is already booked for the selected dates")

    # 4) Price is calculated on the server: nights x current room price (copied, not linked)
    nights = (data.check_out - data.check_in).days
    booking = Booking(
        user_id=user.id,
        room_id=room.id,
        check_in=data.check_in,
        check_out=data.check_out,
        guests=data.guests,
        nightly_rate=room.price_per_night,
        total_price=room.price_per_night * nights,
        status=BookingStatus.ACTIVE,
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The exclusion constraint in PostgreSQL is a second guarantee against overlap
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise ConflictError("Room is already booked for the selected dates") from None
        raise
    db.refresh(booking)
    return booking


def get_booking(db: Session, user: User, booking_id: int, for_update: bool = False) -> Booking:
    """Admin sees any booking; a guest only their own. Someone else's booking is a 404."""
    stmt = select(Booking).where(Booking.id == booking_id)
    if for_update:
        stmt = stmt.with_for_update()
    booking = db.scalar(stmt)
    if booking is None or (not user.is_admin and booking.user_id != user.id):
        raise NotFoundError("Booking not found")
    return booking


def list_my_bookings(
    db: Session, user: User, filters: MyBookingsFilter
) -> tuple[list[Booking], int]:
    stmt = select(Booking).where(Booking.user_id == user.id)
    if filters.status is not None:
        stmt = stmt.where(Booking.status == filters.status)
    stmt = stmt.order_by(Booking.check_in, Booking.id)
    return paginate(db, stmt, filters.page, filters.size)


def list_all_bookings(db: Session, filters: BookingFilter) -> tuple[list[Booking], int]:
    stmt = select(Booking)
    if filters.room_id is not None:
        stmt = stmt.where(Booking.room_id == filters.room_id)
    # Date filter returns stays that intersect [date_from, date_to)
    if filters.date_from is not None:
        stmt = stmt.where(Booking.check_out > filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Booking.check_in < filters.date_to)
    if filters.status is not None:
        stmt = stmt.where(Booking.status == filters.status)
    stmt = stmt.order_by(Booking.check_in, Booking.room_id, Booking.id)
    return paginate(db, stmt, filters.page, filters.size)


def cancel_booking(db: Session, user: User, booking_id: int) -> Booking:
    booking = get_booking(db, user, booking_id, for_update=True)
    if booking.status == BookingStatus.CANCELLED:
        raise ConflictError("Booking is already cancelled")
    # Only future bookings can be cancelled: on the check-in day or later it is refused
    if booking.check_in <= clock.today():
        raise ConflictError("Booking can only be cancelled before the check-in date")

    # Soft cancel: the row stays as history, it just stops blocking the dates
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = datetime.now(UTC)
    db.commit()
    db.refresh(booking)
    return booking
