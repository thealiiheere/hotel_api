"""Test setup: a real PostgreSQL database, migrated with Alembic, emptied before each test.

Tests always use TEST_DATABASE_URL (never DATABASE_URL), so they cannot touch a real database.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:55432/hotel_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-0123456789")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from tests.helpers import create_room, login_headers, make_admin, register  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config("alembic.ini")
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE bookings, rooms, users RESTART IDENTITY CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_headers(client):
    register(client, "admin@hotel.uz", "Admin")
    make_admin("admin@hotel.uz")
    return login_headers(client, "admin@hotel.uz")


@pytest.fixture
def guest_headers(client):
    register(client, "guest@hotel.uz", "Guest One")
    return login_headers(client, "guest@hotel.uz")


@pytest.fixture
def other_guest_headers(client):
    register(client, "other@hotel.uz", "Guest Two")
    return login_headers(client, "other@hotel.uz")


@pytest.fixture
def room(client, admin_headers):
    return create_room(client, admin_headers)
