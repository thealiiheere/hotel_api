from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminUser, DbSession
from app.models.room import Room
from app.schemas.common import Page
from app.schemas.room import AvailabilityQuery, RoomCreate, RoomFilter, RoomOut, RoomUpdate
from app.services import room_service

router = APIRouter(prefix="/rooms", tags=["Rooms"])


# ---------------------------------------------------------------------------
# GET /rooms  (public)
# Paginated list of all rooms, with optional filters:
#   ?min_capacity=2&max_capacity=4    -> by capacity (number of guests)
#   ?min_price=100&max_price=300      -> by price per night
#   ?page=1&size=20                   -> pagination (size max 100)
# ---------------------------------------------------------------------------
@router.get("", response_model=Page[RoomOut])
def list_rooms(db: DbSession, filters: Annotated[RoomFilter, Query()]) -> dict:
    items, total = room_service.list_rooms(db, filters)
    return {"items": items, "total": total, "page": filters.page, "size": filters.size}


# ---------------------------------------------------------------------------
# GET /rooms/available  (public)
# Rooms that are free for the whole period [check_in, check_out) and fit the guests.
#   ?check_in=2026-11-10&check_out=2026-11-12&guests=2
# - a room whose active booking ends on check_in day IS available (half-open period)
# - cancelled bookings do not block a room
# - check_in in the past or check_in >= check_out -> 422
# ---------------------------------------------------------------------------
@router.get("/available", response_model=Page[RoomOut])
def list_available_rooms(db: DbSession, query: Annotated[AvailabilityQuery, Query()]) -> dict:
    items, total = room_service.list_available_rooms(db, query)
    return {"items": items, "total": total, "page": query.page, "size": query.size}


# ---------------------------------------------------------------------------
# GET /rooms/{room_id}  (public)
# Details of one room. Unknown id -> 404.
# ---------------------------------------------------------------------------
@router.get("/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: DbSession) -> Room:
    return room_service.get_room(db, room_id)


# ---------------------------------------------------------------------------
# POST /rooms  (admin only)
# Adds a new room.
# - room number must be unique         -> 409
# - capacity >= 1, price_per_night > 0  -> otherwise 422
# - guest token -> 403, no token -> 401
# ---------------------------------------------------------------------------
@router.post("", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(data: RoomCreate, db: DbSession, _admin: AdminUser) -> Room:
    return room_service.create_room(db, data)


# ---------------------------------------------------------------------------
# PATCH /rooms/{room_id}  (admin only)
# Partially updates a room (send only the fields to change).
# - changing price_per_night does NOT change existing bookings (they keep a price copy)
# - duplicate room number -> 409, unknown id -> 404
# ---------------------------------------------------------------------------
@router.patch("/{room_id}", response_model=RoomOut)
def update_room(room_id: int, data: RoomUpdate, db: DbSession, _admin: AdminUser) -> Room:
    return room_service.update_room(db, room_id, data)


# ---------------------------------------------------------------------------
# DELETE /rooms/{room_id}  (admin only)
# Deletes a room that has never been booked.
# - a room with any booking history (even cancelled) -> 409, so history is never lost
# - unknown id -> 404
# ---------------------------------------------------------------------------
@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(room_id: int, db: DbSession, _admin: AdminUser) -> Response:
    room_service.delete_room(db, room_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
