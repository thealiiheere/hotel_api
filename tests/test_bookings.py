import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core import clock
from app.core.exceptions import ConflictError
from app.db.session import SessionLocal
from app.models import Booking, BookingStatus, User
from app.schemas.booking import BookingCreate
from app.services import booking_service
from tests.helpers import book, create_room, future


@pytest.fixture
def freeze_today(monkeypatch):
    """Call freeze_today(date(...)) to make the app think that day is today."""

    def freeze(day: date) -> None:
        monkeypatch.setattr(clock, "today", lambda: day)

    return freeze


# --- The scenario shown at the defence ------------------------------------------------------


def test_exam_scenario_overlap_and_price(
    client, guest_headers, other_guest_headers, room, freeze_today
):
    """10-12 Nov 2026 is booked -> 11-13 Nov is refused, 12-14 Nov is allowed; 2 nights priced."""
    freeze_today(date(2026, 10, 23))

    first = book(client, guest_headers, room["id"], "2026-11-10", "2026-11-12")
    assert first.status_code == 201
    body = first.json()
    assert body["nights"] == 2
    assert body["nightly_rate"] == 120.5
    assert body["total_price"] == 241.0  # 2 x 120.50, calculated by the server

    overlapping = book(client, other_guest_headers, room["id"], "2026-11-11", "2026-11-13")
    assert overlapping.status_code == 409

    on_checkout_day = book(client, other_guest_headers, room["id"], "2026-11-12", "2026-11-14")
    assert on_checkout_day.status_code == 201


# --- Creating bookings -------------------------------------------------------------------------


def test_price_is_copied_at_booking_time(client, admin_headers, guest_headers, room):
    booking = book(client, guest_headers, room["id"], future(5), future(8)).json()
    assert booking["total_price"] == 361.5  # 3 x 120.50

    client.patch(f"/rooms/{room['id']}", json={"price_per_night": "999"}, headers=admin_headers)

    again = client.get(f"/bookings/{booking['id']}", headers=guest_headers).json()
    assert again["nightly_rate"] == 120.5
    assert again["total_price"] == 361.5


def test_check_in_today_is_allowed(client, guest_headers, room):
    assert book(client, guest_headers, room["id"], future(0), future(1)).status_code == 201


@pytest.mark.parametrize(
    ("check_in", "check_out", "guests"),
    [
        (-1, 2, 1),  # check-in in the past
        (5, 5, 1),  # check-in == check-out
        (6, 5, 1),  # check-out before check-in
        (5, 7, 0),  # zero guests
        (5, 7, -1),  # negative guests
    ],
)
def test_invalid_booking_input_is_422(client, guest_headers, room, check_in, check_out, guests):
    response = book(client, guest_headers, room["id"], future(check_in), future(check_out), guests)
    assert response.status_code == 422


def test_guests_over_capacity_is_422(client, guest_headers, room):
    response = book(client, guest_headers, room["id"], future(5), future(7), guests=3)
    assert response.status_code == 422


def test_booking_unknown_room_is_404(client, guest_headers):
    assert book(client, guest_headers, 99999, future(5), future(7)).status_code == 404


def test_booking_requires_login(client, room):
    assert book(client, {}, room["id"], future(5), future(7)).status_code == 401


def test_user_id_in_body_is_ignored(client, guest_headers, other_guest_headers, room):
    me = client.get("/users/me", headers=guest_headers).json()["id"]
    other = client.get("/users/me", headers=other_guest_headers).json()["id"]
    payload = {
        "room_id": room["id"],
        "check_in": future(5),
        "check_out": future(7),
        "guests": 1,
        "user_id": other,
    }
    response = client.post("/bookings", json=payload, headers=guest_headers)
    assert response.status_code == 201
    assert response.json()["user_id"] == me


def test_cancelled_booking_does_not_block_dates(client, guest_headers, other_guest_headers, room):
    booking = book(client, guest_headers, room["id"], future(10), future(12)).json()
    client.post(f"/bookings/{booking['id']}/cancel", headers=guest_headers)
    response = book(client, other_guest_headers, room["id"], future(10), future(12))
    assert response.status_code == 201


# --- Reading bookings --------------------------------------------------------------------------


def test_guest_sees_only_own_bookings(
    client, admin_headers, guest_headers, other_guest_headers, room
):
    mine = book(client, guest_headers, room["id"], future(5), future(7)).json()
    theirs = book(client, other_guest_headers, room["id"], future(10), future(12)).json()

    my_list = client.get("/bookings/me", headers=guest_headers).json()
    assert [b["id"] for b in my_list["items"]] == [mine["id"]]
    assert my_list["total"] == 1

    assert client.get(f"/bookings/{mine['id']}", headers=guest_headers).status_code == 200
    # Someone else's booking is hidden behind 404, not revealed with 403
    assert client.get(f"/bookings/{theirs['id']}", headers=guest_headers).status_code == 404
    assert client.get(f"/bookings/{theirs['id']}", headers=admin_headers).status_code == 200
    assert client.get("/bookings/99999", headers=guest_headers).status_code == 404


def test_admin_lists_all_bookings_by_room_and_date(
    client, admin_headers, guest_headers, other_guest_headers
):
    room1 = create_room(client, admin_headers, number="101")
    room2 = create_room(client, admin_headers, number="102")
    b1 = book(client, guest_headers, room1["id"], future(10), future(12)).json()
    b2 = book(client, other_guest_headers, room2["id"], future(10), future(12)).json()
    b3 = book(client, guest_headers, room1["id"], future(20), future(22)).json()

    def ids(**params):
        response = client.get("/bookings", params=params, headers=admin_headers)
        assert response.status_code == 200, response.text
        return {b["id"] for b in response.json()["items"]}

    assert ids() == {b1["id"], b2["id"], b3["id"]}
    assert ids(room_id=room1["id"]) == {b1["id"], b3["id"]}
    assert ids(date_from=future(19), date_to=future(25)) == {b3["id"]}
    assert ids(room_id=room2["id"], date_from=future(9), date_to=future(11)) == {b2["id"]}

    page = client.get("/bookings", params={"size": 2}, headers=admin_headers).json()
    assert page["total"] == 3 and len(page["items"]) == 2

    assert client.get("/bookings", headers=guest_headers).status_code == 403


# --- Cancelling --------------------------------------------------------------------------------


def test_cancel_future_booking_keeps_history(client, guest_headers, room):
    booking = book(client, guest_headers, room["id"], future(5), future(7)).json()

    response = client.post(f"/bookings/{booking['id']}/cancel", headers=guest_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None

    again = client.post(f"/bookings/{booking['id']}/cancel", headers=guest_headers)
    assert again.status_code == 409

    cancelled = client.get("/bookings/me", params={"status": "cancelled"}, headers=guest_headers)
    assert [b["id"] for b in cancelled.json()["items"]] == [booking["id"]]


def test_cancel_on_or_after_check_in_day_is_409(client, guest_headers, room, freeze_today):
    freeze_today(date(2026, 10, 23))
    booking = book(client, guest_headers, room["id"], "2026-11-10", "2026-11-12").json()
    url = f"/bookings/{booking['id']}/cancel"

    freeze_today(date(2026, 11, 10))  # check-in day
    assert client.post(url, headers=guest_headers).status_code == 409
    freeze_today(date(2026, 11, 11))  # during the stay
    assert client.post(url, headers=guest_headers).status_code == 409
    freeze_today(date(2026, 11, 9))  # one day before
    assert client.post(url, headers=guest_headers).status_code == 200


def test_only_owner_or_admin_can_cancel(
    client, admin_headers, guest_headers, other_guest_headers, room
):
    booking = book(client, guest_headers, room["id"], future(5), future(7)).json()
    url = f"/bookings/{booking['id']}/cancel"
    assert client.post(url, headers=other_guest_headers).status_code == 404
    assert client.post(url, headers=admin_headers).status_code == 200


# --- Concurrency and database guarantees -------------------------------------------------------


def test_parallel_requests_create_only_one_booking(guest_headers, room):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "guest@hotel.uz"))
    data = BookingCreate(room_id=room["id"], check_in=future(30), check_out=future(33), guests=1)

    attempts = 8
    barrier = threading.Barrier(attempts)
    results: list[str] = []

    def attempt() -> None:
        with SessionLocal() as db:
            barrier.wait()  # all threads hit the service at the same moment
            try:
                booking_service.create_booking(db, user, data)
                results.append("created")
            except ConflictError:
                results.append("conflict")

    threads = [threading.Thread(target=attempt) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("created") == 1
    assert results.count("conflict") == attempts - 1


def test_database_constraints_block_overlap_and_wrong_total(guest_headers, room):
    today = clock.today()

    def new_booking(start: int, end: int, **overrides) -> Booking:
        rate = Decimal("100.00")
        fields = {
            "user_id": 1,
            "room_id": room["id"],
            "check_in": today + timedelta(days=start),
            "check_out": today + timedelta(days=end),
            "guests": 1,
            "nightly_rate": rate,
            "total_price": rate * (end - start),
            "status": BookingStatus.ACTIVE,
        }
        return Booking(**(fields | overrides))

    with SessionLocal() as db:
        db.add(new_booking(10, 12))
        db.commit()

        # Overlapping active booking inserted directly (bypassing the service) is still rejected
        db.add(new_booking(11, 13))
        with pytest.raises(IntegrityError, match="ex_bookings_no_overlap"):
            db.commit()
        db.rollback()

        # Cancelled rows never block, adjacent rows are fine
        db.add(new_booking(11, 13, status=BookingStatus.CANCELLED, cancelled_at=datetime.now(UTC)))
        db.add(new_booking(12, 14))
        db.commit()

        # total_price must equal nightly_rate x nights
        db.add(new_booking(20, 22, total_price=Decimal("1.00")))
        with pytest.raises(IntegrityError, match="ck_bookings_total_price_matches"):
            db.commit()
        db.rollback()
