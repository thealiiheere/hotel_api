"""Single source of "today" for business rules.

Kept in its own module so tests can freeze the date
(monkeypatch app.core.clock.today) without touching the system clock.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def today() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()
