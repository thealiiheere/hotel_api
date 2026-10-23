# Hotel Booking API

FastAPI + PostgreSQL API for hotel rooms and nightly bookings.
A guest picks a free room for given dates; the server calculates the number of nights and the total price.

**Stack:** FastAPI · PostgreSQL · SQLAlchemy 2 · Pydantic 2 · Alembic · JWT (PyJWT + bcrypt) · GitHub Actions · AWS EC2 · Nginx · systemd

Live: `http://13.218.229.242/docs` (Swagger UI) · health: `http://13.218.229.242/health`

## Roles

| Role  | Can do |
|-------|--------|
| admin | add / edit / delete rooms, see and cancel **all** bookings, list bookings by room and date |
| guest | create, view and cancel **only own** bookings |

Registration always creates a `guest` (a `role` field in the body is ignored).
The first admin is created on the server with a script (see below).

## Endpoints

| Method | Path | Access | Description |
|--------|------|--------|-------------|
| POST | `/auth/register` | public | Register (unique email, bcrypt hash) |
| POST | `/auth/login` | public | Get a JWT access token (expires) |
| GET | `/users/me` | user | Own profile (no password hash) |
| GET | `/rooms` | public | Rooms list, filters `min_capacity`, `max_capacity`, `min_price`, `max_price`, pagination |
| GET | `/rooms/available` | public | Free rooms for `check_in`, `check_out`, `guests` |
| GET | `/rooms/{id}` | public | Room detail |
| POST | `/rooms` | admin | Create room |
| PATCH | `/rooms/{id}` | admin | Update room |
| DELETE | `/rooms/{id}` | admin | Delete room (409 if it has booking history) |
| POST | `/bookings` | user | Book a room, price calculated by the server |
| GET | `/bookings/me` | user | Own bookings, pagination, `status` filter |
| GET | `/bookings/{id}` | owner / admin | Booking detail (someone else's -> 404) |
| POST | `/bookings/{id}/cancel` | owner / admin | Cancel a future booking |
| GET | `/bookings` | admin | All bookings, filters `room_id`, `date_from`, `date_to`, `status` |
| GET | `/health` | public | App + DB health check |

All lists return `{"items": [...], "total": N, "page": 1, "size": 20}` (`?page=&size=`, size max 100).

## Business rules and where they are enforced

| Rule | Enforced by |
|------|-------------|
| `check_in >= today`, `check_in < check_out`, `guests >= 1` | Pydantic validator -> **422**; DB `CHECK` constraints |
| guests <= room capacity | service -> **422** |
| Period is `[check_in, check_out)`: check-out day can be the next check-in | overlap query `a.check_in < b.check_out AND a.check_out > b.check_in` |
| Active bookings of a room never overlap, also under parallel requests | `SELECT ... FOR UPDATE` on the room row **and** PostgreSQL `EXCLUDE USING gist` constraint -> **409** |
| Cancelled bookings do not block dates | `WHERE status = 'active'` in the query and in the exclusion constraint |
| `total_price = nights x nightly_rate`, rate copied at booking time | service + DB `CHECK (total_price = nightly_rate * (check_out - check_in))` |
| Cancel only before the check-in day | service -> **409** |
| History is never deleted by accident | cancel = status change; FKs `ON DELETE RESTRICT`; room with bookings -> **409** |
| Owner / role checked on the server | user id and role always come from the JWT + DB, never from the request body |

Status codes: 401 no/invalid/expired token · 403 not admin · 404 not found (or someone else's booking) · 409 business conflict · 422 invalid input.

## Project structure

```
app/
  main.py              FastAPI app, routers, error -> HTTP mapping
  core/                config (env), security (bcrypt, JWT), clock (today), domain errors
  db/                  engine/session, declarative base, pagination helper
  models/              SQLAlchemy models: User, Room, Booking
  schemas/             Pydantic request/response models and validation
  services/            business logic (no HTTP here)
  api/deps.py          DB session, current user from JWT, admin check
  api/routers/         one file per resource, a comment block above every endpoint
  scripts/create_admin.py
alembic/versions/      migrations (tables + all constraints)
tests/                 pytest against real PostgreSQL
deploy/                setup_server.sh, deploy.sh, systemd unit, nginx config
.github/workflows/     CI/CD pipeline
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                     # then edit DATABASE_URL and SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload                            # http://127.0.0.1:8000/docs
```

### Tests

Tests need an empty PostgreSQL database (they run the migrations themselves):

```bash
docker run -d --name hotel-test-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=hotel_test -p 55432:5432 postgres:18
pytest                         # uses TEST_DATABASE_URL, default localhost:55432/hotel_test
ruff check . && ruff format --check .
```

### Create an admin

```bash
python -m app.scripts.create_admin --email admin@hotel.uz --full-name "Hotel Admin"
```

On the server: `cd /opt/hotel-api && .venv/bin/python -m app.scripts.create_admin --email ...`

## CI/CD

`.github/workflows/ci-cd.yml`

1. **lint** – `ruff check`, `ruff format --check`
2. **test** – PostgreSQL 18 service container, `alembic upgrade head / downgrade base / upgrade head` on an empty DB, then `pytest`
3. **deploy** – only on push to `main` and only if lint **and** test passed: SSH to EC2 -> `deploy/deploy.sh`
   (git pull -> pip install -> `alembic upgrade head` -> `systemctl restart hotel-api` -> `GET /health`),
   then a public `GET http://<EC2_HOST>/health` through Nginx

Repository settings needed:

| Kind | Name | Value |
|------|------|-------|
| Variable | `EC2_HOST` | server IP |
| Variable | `EC2_USER` | `ubuntu` |
| Secret | `EC2_SSH_KEY` | private key of a dedicated deploy key |

## Server (EC2, Ubuntu)

One-time bootstrap: `sudo bash deploy/setup_server.sh https://github.com/thealiiheere/hotel_api.git`
installs PostgreSQL, Nginx and Python, generates the DB password and `SECRET_KEY` into `/opt/hotel-api/.env`
(chmod 600, never in git), installs the `hotel-api` systemd service and the Nginx reverse proxy (port 80 -> 127.0.0.1:8000).

Useful commands: `systemctl status hotel-api` · `journalctl -u hotel-api -f` · `sudo nginx -t`

## Defence demo (10–12 Nov 2026)

In Swagger (`/docs`): log in as admin, **Authorize** with the token, create a room with `price_per_night: 500000`.
Then as a guest:

1. `POST /bookings` `{"room_id": 1, "check_in": "2026-11-10", "check_out": "2026-11-12", "guests": 2}` -> **201**, `nights: 2`, `total_price: 1000000`
2. same room, `2026-11-11` -> `2026-11-13` -> **409** (overlap)
3. same room, `2026-11-12` -> `2026-11-14` -> **201** (check-out day is free)

The same scenario is an automated test: `tests/test_bookings.py::test_exam_scenario_overlap_and_price`.
