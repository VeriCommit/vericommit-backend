"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from vericommit_backend.api.router import api_router
from vericommit_backend.api.routes.health import router as health_router
from vericommit_backend.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    return application


app = create_app()
