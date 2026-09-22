"""
Common Response Schemas

Envelope contract (frontend relies on it):
- success -> ``code == SUCCESS_CODE`` (200)
- business error -> ``code`` is the HTTP-like status (400/401/403/404/409/429/500)
  with a human-readable ``msg``. Do **not** use 0/1 — the frontend treats any
  non-200 code as failure and routes 401/403 to the login page.
"""
from typing import Generic, TypeVar, Optional, List

from pydantic import BaseModel

T = TypeVar("T")

SUCCESS_CODE = 200


class Response(BaseModel, Generic[T]):
    """Standard API response"""
    code: int = SUCCESS_CODE
    msg: str = "success"
    data: Optional[T] = None


class PaginatedData(BaseModel, Generic[T]):
    """Paginated data structure"""
    total: int
    page: int
    page_size: int
    list: List[T]


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated API response"""
    code: int = SUCCESS_CODE
    data: PaginatedData[T]
