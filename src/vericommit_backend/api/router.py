"""Versioned API router."""

from fastapi import APIRouter

from vericommit_backend.api.routes.evaluations import router as evaluations_router

api_router = APIRouter()
api_router.include_router(evaluations_router)
