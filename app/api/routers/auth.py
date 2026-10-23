from fastapi import APIRouter, status

from app.api.deps import DbSession
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# POST /auth/register  (public)
# Creates a new account with role "guest".
# - email is unique (case-insensitive)          -> 409 if already registered
# - password is stored only as a bcrypt hash    -> never returned in any response
# - a "role" field in the body is ignored, so nobody can register as admin
# - invalid email / short password              -> 422
# ---------------------------------------------------------------------------
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession) -> User:
    return auth_service.register_user(db, data)


# ---------------------------------------------------------------------------
# POST /auth/login  (public)
# Checks email + password and returns a JWT access token with an expiry ("exp").
# - wrong email or wrong password -> 401 (same message for both)
# - use the token as header:  Authorization: Bearer <access_token>
# ---------------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    token = auth_service.login(db, data.email, data.password)
    return TokenResponse(access_token=token, expires_in=settings.access_token_expire_minutes * 60)
