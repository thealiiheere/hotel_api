from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession

router = APIRouter(tags=["Health"])


# ---------------------------------------------------------------------------
# GET /health  (public)
# Used by the deploy pipeline after every release.
# 200 {"status": "ok"} when the app and the database respond, otherwise 503.
# ---------------------------------------------------------------------------
@router.get("/health", response_model=None)
def health(db: DbSession) -> dict | JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "error", "database": "down"})
    return {"status": "ok", "database": "ok"}
