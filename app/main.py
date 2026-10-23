"""FastAPI application: routers + mapping of domain errors to HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routers import auth, bookings, health, rooms, users
from app.core.config import settings
from app.core.exceptions import AppError

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Hotel rooms and nightly bookings. Admin manages rooms and all bookings; "
        "a guest creates, views and cancels only their own bookings."
    ),
)


@app.exception_handler(AppError)
def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
    # 401 / 403 / 404 / 409 / 422 raised by the service layer
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


@app.exception_handler(IntegrityError)
def handle_integrity_error(_request: Request, _exc: IntegrityError) -> JSONResponse:
    # Safety net: any DB constraint violation not handled in a service is a conflict, not a 500
    return JSONResponse(status_code=409, content={"detail": "Request conflicts with existing data"})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(rooms.router)
app.include_router(bookings.router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
