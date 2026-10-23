from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core import clock
from app.db.session import SessionLocal
from app.models.user import User, UserRole

PASSWORD = "secret-pass-123"


def register(client: TestClient, email: str, full_name: str = "Test User") -> dict:
    response = client.post(
        "/auth/register", json={"email": email, "full_name": full_name, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_headers(client: TestClient, email: str) -> dict:
    response = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_admin(email: str) -> None:
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == email).values(role=UserRole.ADMIN))
        db.commit()


def create_room(client: TestClient, headers: dict, **overrides) -> dict:
    payload = {"number": "101", "room_type": "Standard", "capacity": 2, "price_per_night": "120.50"}
    payload.update(overrides)
    response = client.post("/rooms", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def future(days: int) -> str:
    """ISO date `days` after today."""
    return (clock.today() + timedelta(days=days)).isoformat()


def book(client: TestClient, headers: dict, room_id: int, check_in, check_out, guests: int = 1):
    if isinstance(check_in, date):
        check_in, check_out = check_in.isoformat(), check_out.isoformat()
    return client.post(
        "/bookings",
        json={"room_id": room_id, "check_in": check_in, "check_out": check_out, "guests": guests},
        headers=headers,
    )
