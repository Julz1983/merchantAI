import uuid
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str


class Envelope(BaseModel, Generic[T]):
    """
    Every API response uses this shape: { data, meta, error }.
    Keeps the shared TS client in packages/types simple — one envelope type
    to unwrap regardless of endpoint.
    """

    data: T | None = None
    meta: Meta
    error: dict[str, Any] | None = None


def envelope(data: Any) -> dict:
    return {"data": data, "meta": {"request_id": str(uuid.uuid4())}, "error": None}
