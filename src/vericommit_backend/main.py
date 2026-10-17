"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException

from vericommit_backend.api.errors import (
    ai_evaluation_error_handler,
    evaluation_not_configured_handler,
    evidence_provider_error_handler,
    request_parsing_error_handler,
    request_validation_error_handler,
    unexpected_error_handler,
)
from vericommit_backend.api.openapi import configure_openapi
from vericommit_backend.api.router import api_router
from vericommit_backend.api.routes.health import router as health_router
from vericommit_backend.config import Settings
from vericommit_backend.evidence.providers import EvidenceProviderError
from vericommit_backend.services.ai import AIEvaluationError
from vericommit_backend.services.diagnostics import configure_safe_logging
from vericommit_backend.services.evaluation import EvaluationNotConfiguredError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    configure_safe_logging()
    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.state.settings = settings
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api/v1")
    application.add_exception_handler(
        RequestValidationError, request_validation_error_handler
    )
    application.add_exception_handler(HTTPException, request_parsing_error_handler)
    application.add_exception_handler(ResponseValidationError, unexpected_error_handler)
    application.add_exception_handler(
        EvaluationNotConfiguredError, evaluation_not_configured_handler
    )

    @application.middleware("http")
    async def safe_unexpected_errors(request: Request, call_next):
        # An Exception handler alone is insufficient: ServerErrorMiddleware
        # re-raises unexpected exceptions after responding, leaking server traces.
        try:
            return await call_next(request)
        except Exception as exc:
            return await unexpected_error_handler(request, exc)

    # Added last so browser clients also receive CORS headers on safe errors.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    application.add_exception_handler(AIEvaluationError, ai_evaluation_error_handler)
    application.add_exception_handler(
        EvidenceProviderError, evidence_provider_error_handler
    )
    configure_openapi(application)
    return application


app = create_app()
