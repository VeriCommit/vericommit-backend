"""Contract errors needed by request validation and the unconfigured service.

Provider-specific errors, timeouts and other BE-10 safeguards remain later work.
"""

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from vericommit_backend.schemas import ErrorDetail, ErrorResponse
from vericommit_backend.services.evaluation import EvaluationNotConfiguredError


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json")
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Choose the specific URL code even if parsing found other field errors too.
    # Missing/null/wrong-type fields remain generic request-validation failures.
    invalid_url = any(
        error["loc"] == ("body", "repository_url") and error["type"] == "value_error"
        for error in exc.errors()
    )
    if invalid_url:
        return error_response(
            400,
            "INVALID_REPOSITORY_URL",
            "Provide a valid HTTPS GitHub repository URL with an owner and repository.",
        )
    return error_response(
        400,
        "INVALID_REQUEST",
        "Provide all required fields with valid types, a supported evidence source, "
        "and at least one nonblank acceptance criterion.",
    )


async def request_parsing_error_handler(request: Request, exc: HTTPException):
    # Invalid body encodings can fail before FastAPI raises RequestValidationError.
    if exc.status_code == 400:
        return error_response(
            400, "INVALID_REQUEST", "Provide a valid JSON request body."
        )
    return await http_exception_handler(request, exc)


async def evaluation_not_configured_handler(
    request: Request, exc: EvaluationNotConfiguredError
) -> JSONResponse:
    return error_response(
        502,
        "EVALUATION_FAILED",
        "The evaluation service is not configured. No evaluation was performed.",
    )
