"""Room management, filtering and availability search."""

from datetime import date

from sqlalchemy import ColumnElement, Select, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.pagination import paginate
from app.models.booking import Booking, BookingStatus
from app.models.room import Room
from app.schemas.room import AvailabilityQuery, RoomCreate, RoomFilter, RoomUpdate


def _ensure_number_free(db: Session, number: str, exclude_room_id: int | None = None) -> None:
    stmt = select(Room.id).where(Room.number == number)
    if exclude_room_id is not None:
        stmt = stmt.where(Room.id != exclude_room_id)
    if db.scalar(stmt) is not None:
        raise ConflictError(f"Room number '{number}' already exists")


def _commit_room(db: Session, room: Room) -> Room:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f"Room number '{room.number}' already exists") from None
    db.refresh(room)
    return room


def create_room(db: Session, data: RoomCreate) -> Room:
    _ensure_number_free(db, data.number)
    room = Room(**data.model_dump())
    db.add(room)
    return _commit_room(db, room)


def get_room(db: Session, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise NotFoundError("Room not found")
    return room


def list_rooms(db: Session, filters: RoomFilter) -> tuple[list[Room], int]:
    stmt = select(Room).order_by(Room.id)
    if filters.min_capacity is not None:
        stmt = stmt.where(Room.capacity >= filters.min_capacity)
    if filters.max_capacity is not None:
        stmt = stmt.where(Room.capacity <= filters.max_capacity)
    if filters.min_price is not None:
        stmt = stmt.where(Room.price_per_night >= filters.min_price)
    if filters.max_price is not None:
        stmt = stmt.where(Room.price_per_night <= filters.max_price)
    return paginate(db, stmt, filters.page, filters.size)


def overlapping_bookings(
    room_id: int | ColumnElement[int], check_in: date, check_out: date
) -> Select[tuple[int]]:
    """Active bookings of a room that intersect the half-open period [check_in, check_out).

    Two periods overlap when existing.check_in < new.check_out
                         AND existing.check_out > new.check_in.
    Touching periods (one ends on the day the other starts) do not overlap.
    """
    return select(Booking.id).where(
        Booking.room_id == room_id,
        Booking.status == BookingStatus.ACTIVE,
        Booking.check_in < check_out,
        Booking.check_out > check_in,
    )


def list_available_rooms(db: Session, query: AvailabilityQuery) -> tuple[list[Room], int]:
    stmt = (
        select(Room)
        .where(Room.capacity >= query.guests)
        .where(~exists(overlapping_bookings(Room.id, query.check_in, query.check_out)))
        .order_by(Room.price_per_night, Room.id)
    )
    return paginate(db, stmt, query.page, query.size)


def update_room(db: Session, room_id: int, data: RoomUpdate) -> Room:
    room = get_room(db, room_id)
    changes = data.model_dump(exclude_unset=True)
    if "number" in changes and changes["number"] != room.number:
        _ensure_number_free(db, changes["number"], exclude_room_id=room.id)
    # Existing bookings keep their own nightly_rate copy, so a price change is safe
    for field, value in changes.items():
        setattr(room, field, value)
    return _commit_room(db, room)


def delete_room(db: Session, room_id: int) -> None:
    # Lock the room so nobody can book it while we check its history
    room = db.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if room is None:
        raise NotFoundError("Room not found")
    if db.scalar(select(exists().where(Booking.room_id == room.id))):
        raise ConflictError("Room has booking history and cannot be deleted")
    db.delete(room)
    try:
        db.commit()
    except IntegrityError:  # FK RESTRICT is the last line of defence
        db.rollback()
        raise ConflictError("Room has booking history and cannot be deleted") from None
