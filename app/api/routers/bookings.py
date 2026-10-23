from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingFilter, BookingOut, MyBookingsFilter
from app.schemas.common import Page
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["Bookings"])


# ---------------------------------------------------------------------------
# POST /bookings  (any logged-in user)
# Books a room for the token's user and calculates the price on the server.
#   body: {"room_id": 1, "check_in": "2026-11-10", "check_out": "2026-11-12", "guests": 2}
# - total_price = nights x room price at booking time (nightly_rate is copied)
# - check_in before today, check_in >= check_out, guests < 1   -> 422
# - guests more than room capacity                             -> 422
# - room does not exist                                        -> 404
# - overlaps an active booking of the same room                -> 409
#   e.g. 10-12 Nov exists: 11-13 Nov is refused, 12-14 Nov is allowed
# - safe under parallel requests: room row lock + DB exclusion constraint
# ---------------------------------------------------------------------------
@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(data: BookingCreate, db: DbSession, user: CurrentUser) -> Booking:
    return booking_service.create_booking(db, user, data)


# ---------------------------------------------------------------------------
# GET /bookings/me  (any logged-in user)
# Paginated list of the current user's own bookings.
#   ?status=active|cancelled&page=1&size=20
# ---------------------------------------------------------------------------
@router.get("/me", response_model=Page[BookingOut])
def list_my_bookings(
    db: DbSession, user: CurrentUser, filters: Annotated[MyBookingsFilter, Query()]
) -> dict:
    items, total = booking_service.list_my_bookings(db, user, filters)
    return {"items": items, "total": total, "page": filters.page, "size": filters.size}


# ---------------------------------------------------------------------------
# GET /bookings  (admin only)
# Paginated list of ALL bookings, filtered by room and date:
#   ?room_id=1                              -> bookings of one room
#   ?date_from=2026-11-01&date_to=2026-12-01 -> stays that intersect this period
#   ?status=active|cancelled
# - guest token -> 403
# ---------------------------------------------------------------------------
@router.get("", response_model=Page[BookingOut])
def list_all_bookings(
    db: DbSession, _admin: AdminUser, filters: Annotated[BookingFilter, Query()]
) -> dict:
    items, total = booking_service.list_all_bookings(db, filters)
    return {"items": items, "total": total, "page": filters.page, "size": filters.size}


# ---------------------------------------------------------------------------
# GET /bookings/{booking_id}  (owner or admin)
# Details of one booking.
# - another guest's booking -> 404 (we do not reveal that it exists)
# ---------------------------------------------------------------------------
@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: DbSession, user: CurrentUser) -> Booking:
    return booking_service.get_booking(db, user, booking_id)


# ---------------------------------------------------------------------------
# POST /bookings/{booking_id}/cancel  (owner or admin)
# Cancels a future booking. The row is kept (status = "cancelled") as history
# and its dates become free for other guests.
# - on the check-in day or later -> 409
# - already cancelled            -> 409
# - another guest's booking      -> 404
# ---------------------------------------------------------------------------
@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: DbSession, user: CurrentUser) -> Booking:
    return booking_service.cancel_booking(db, user, booking_id)
