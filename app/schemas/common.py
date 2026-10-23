from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

# Stored and calculated as Decimal (exact), sent to clients as a JSON number
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int
