from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User
from tests.helpers import PASSWORD, login_headers, register


def test_register_creates_guest_without_exposing_password(client):
    response = client.post(
        "/auth/register",
        json={"email": "Ali@Hotel.uz", "full_name": "Ali", "password": PASSWORD, "role": "admin"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ali@hotel.uz"
    assert body["role"] == "guest"  # "role": "admin" in the body is ignored
    assert "password" not in body and "password_hash" not in body

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "ali@hotel.uz"))
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("$2b$")  # bcrypt


def test_register_duplicate_email_is_409(client):
    register(client, "ali@hotel.uz")
    response = client.post(
        "/auth/register", json={"email": "ALI@hotel.uz", "full_name": "Ali", "password": PASSWORD}
    )
    assert response.status_code == 409


def test_register_invalid_input_is_422(client):
    bad_email = {"email": "not-an-email", "full_name": "Ali", "password": PASSWORD}
    short_password = {"email": "ali@hotel.uz", "full_name": "Ali", "password": "123"}
    assert client.post("/auth/register", json=bad_email).status_code == 422
    assert client.post("/auth/register", json=short_password).status_code == 422


def test_login_returns_expiring_jwt(client):
    register(client, "ali@hotel.uz")
    response = client.post("/auth/login", json={"email": "ali@hotel.uz", "password": PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(body["access_token"], settings.secret_key, algorithms=["HS256"])
    assert "exp" in payload


def test_login_wrong_credentials_is_401(client):
    register(client, "ali@hotel.uz")
    wrong_password = {"email": "ali@hotel.uz", "password": "wrong-password"}
    unknown_email = {"email": "nobody@hotel.uz", "password": PASSWORD}
    assert client.post("/auth/login", json=wrong_password).status_code == 401
    assert client.post("/auth/login", json=unknown_email).status_code == 401


def test_me_returns_own_profile_without_password(client):
    register(client, "ali@hotel.uz", "Ali Valiyev")
    response = client.get("/users/me", headers=login_headers(client, "ali@hotel.uz"))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ali@hotel.uz"
    assert body["full_name"] == "Ali Valiyev"
    assert "password_hash" not in body


def test_me_rejects_missing_invalid_and_expired_tokens(client):
    user = register(client, "ali@hotel.uz")
    expired = jwt.encode(
        {"sub": str(user["id"]), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm="HS256",
    )
    forged = jwt.encode(
        {"sub": str(user["id"]), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "some-other-secret-key-that-is-long-enough",
        algorithm="HS256",
    )
    assert client.get("/users/me").status_code == 401
    for token in ("garbage", expired, forged):
        response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
