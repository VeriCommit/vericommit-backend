"""Process liveness endpoint, independent of future external providers."""

from typing import Literal

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, Literal["ok"]]:
    return {"status": "ok"}
