from fastapi import APIRouter

from core.response import envelope

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return envelope({"status": "ok"})
