"""
Common Response Schemas
"""
from typing import Generic, TypeVar, Optional, List, Any
from pydantic import BaseModel

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """Standard API response"""
    code: int = 200
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
    code: int = 200
    data: PaginatedData[T]
