from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["Users"])


# ---------------------------------------------------------------------------
# GET /users/me  (any logged-in user)
# Returns the profile of the token's owner.
# - no token / invalid token / expired token -> 401
# - response schema UserOut has no password_hash field
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser) -> User:
    return user
