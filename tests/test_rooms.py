from tests.helpers import book, create_room, future


def test_admin_creates_room(client, admin_headers):
    room = create_room(client, admin_headers, number="201", capacity=3, price_per_night="250.00")
    assert room["number"] == "201"
    assert room["capacity"] == 3
    assert room["price_per_night"] == 250.0


def test_guest_cannot_manage_rooms(client, guest_headers, room):
    payload = {"number": "999", "room_type": "Suite", "capacity": 2, "price_per_night": "10"}
    assert client.post("/rooms", json=payload, headers=guest_headers).status_code == 403
    assert client.post("/rooms", json=payload).status_code == 401
    patch = client.patch(f"/rooms/{room['id']}", json={"capacity": 5}, headers=guest_headers)
    assert patch.status_code == 403
    assert client.delete(f"/rooms/{room['id']}", headers=guest_headers).status_code == 403


def test_duplicate_room_number_is_409(client, admin_headers, room):
    payload = {"number": "101", "room_type": "Suite", "capacity": 2, "price_per_night": "10"}
    assert client.post("/rooms", json=payload, headers=admin_headers).status_code == 409


def test_invalid_room_is_422(client, admin_headers):
    base = {"number": "300", "room_type": "Suite", "capacity": 2, "price_per_night": "10"}
    for bad in ({"capacity": 0}, {"price_per_night": "-5"}, {"price_per_night": "0"}):
        response = client.post("/rooms", json=base | bad, headers=admin_headers)
        assert response.status_code == 422, bad


def test_room_list_pagination_and_filters(client, admin_headers):
    create_room(client, admin_headers, number="101", capacity=1, price_per_night="80")
    create_room(client, admin_headers, number="102", capacity=2, price_per_night="120")
    create_room(client, admin_headers, number="103", capacity=4, price_per_night="300")

    page1 = client.get("/rooms", params={"page": 1, "size": 2}).json()
    page2 = client.get("/rooms", params={"page": 2, "size": 2}).json()
    assert page1["total"] == 3 and len(page1["items"]) == 2
    assert len(page2["items"]) == 1

    by_capacity = client.get("/rooms", params={"min_capacity": 2}).json()
    assert {r["number"] for r in by_capacity["items"]} == {"102", "103"}

    by_price = client.get("/rooms", params={"min_price": 100, "max_price": 200}).json()
    assert [r["number"] for r in by_price["items"]] == ["102"]

    assert client.get("/rooms", params={"min_price": 300, "max_price": 100}).status_code == 422
    assert client.get("/rooms", params={"size": 1000}).status_code == 422


def test_room_detail_and_404(client, room):
    assert client.get(f"/rooms/{room['id']}").json()["number"] == "101"
    assert client.get("/rooms/99999").status_code == 404


def test_admin_updates_room(client, admin_headers, room):
    response = client.patch(
        f"/rooms/{room['id']}", json={"price_per_night": "150.00"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["price_per_night"] == 150.0
    assert response.json()["capacity"] == room["capacity"]  # untouched fields stay

    null_capacity = client.patch(
        f"/rooms/{room['id']}", json={"capacity": None}, headers=admin_headers
    )
    assert null_capacity.status_code == 422
    missing = client.patch("/rooms/99999", json={"capacity": 3}, headers=admin_headers)
    assert missing.status_code == 404


def test_update_to_existing_number_is_409(client, admin_headers, room):
    other = create_room(client, admin_headers, number="102")
    response = client.patch(f"/rooms/{other['id']}", json={"number": "101"}, headers=admin_headers)
    assert response.status_code == 409


def test_delete_room_without_bookings(client, admin_headers, room):
    assert client.delete(f"/rooms/{room['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/rooms/{room['id']}").status_code == 404
    assert client.delete(f"/rooms/{room['id']}", headers=admin_headers).status_code == 404


def test_delete_room_with_booking_history_is_409(client, admin_headers, guest_headers, room):
    booking = book(client, guest_headers, room["id"], future(5), future(7)).json()
    client.post(f"/bookings/{booking['id']}/cancel", headers=guest_headers)
    # Even a cancelled booking is history that must not be erased
    assert client.delete(f"/rooms/{room['id']}", headers=admin_headers).status_code == 409


def test_available_rooms(client, admin_headers, guest_headers):
    small = create_room(client, admin_headers, number="101", capacity=1)
    create_room(client, admin_headers, number="102", capacity=4)
    book(client, guest_headers, small["id"], future(10), future(12))

    def available(check_in, check_out, guests=1):
        params = {"check_in": check_in, "check_out": check_out, "guests": guests}
        return {r["number"] for r in client.get("/rooms/available", params=params).json()["items"]}

    assert available(future(11), future(13)) == {"102"}  # overlaps the booking
    assert available(future(12), future(14)) == {"101", "102"}  # starts on check-out day
    assert available(future(8), future(10)) == {"101", "102"}  # ends on check-in day
    assert available(future(1), future(3), guests=3) == {"102"}  # capacity filter


def test_cancelled_booking_frees_availability(client, guest_headers, room):
    booking = book(client, guest_headers, room["id"], future(10), future(12)).json()
    client.post(f"/bookings/{booking['id']}/cancel", headers=guest_headers)
    params = {"check_in": future(10), "check_out": future(12)}
    items = client.get("/rooms/available", params=params).json()["items"]
    assert [r["id"] for r in items] == [room["id"]]


def test_available_rooms_invalid_dates_is_422(client):
    past = {"check_in": future(-1), "check_out": future(2)}
    reversed_dates = {"check_in": future(5), "check_out": future(5)}
    assert client.get("/rooms/available", params=past).status_code == 422
    assert client.get("/rooms/available", params=reversed_dates).status_code == 422
