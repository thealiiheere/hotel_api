"""Shared FastAPI dependencies: DB session, current user from JWT, admin check."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(
    auto_error=False, description="Paste the access_token returned by POST /auth/login"
)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the user from the Bearer token. Missing, invalid or expired token -> 401."""
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise AuthenticationError("Invalid or expired token")
    # The role is always read from the database, never from the token or the request
    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
