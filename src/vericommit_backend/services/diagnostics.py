"""Allowlisted failure diagnostics; never serialize exceptions or upstream bodies."""

import logging

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class _SuppressTransportDetails(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


_TRANSPORT_FILTER = _SuppressTransportDetails()


def configure_safe_logging() -> None:
    # These emit URLs, headers, ASGI scopes or provider bodies at verbose levels.
    # Our own allowlisted diagnostics retain component/category/status instead.
    for name in (
        "openai._base_client",
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
        "uvicorn.asgi",
        "uvicorn.access",
    ):
        logging.getLogger(name).addFilter(_TRANSPORT_FILTER)


_PROVIDER_ACTIONS = {
    "insufficient_quota": "Check API project billing, credits and spending limits.",
    "invalid_api_key": "Check the server API key and its project permissions.",
    "model_not_found": "Check model availability and project access.",
    "invalid_json_schema": "Check the model's supported structured-output schema.",
    "unsupported_parameter": "Check request parameters supported by the model.",
    "rate_limit_exceeded": "Check project rate limits and request volume.",
}


def log_failure(component: str, exc: Exception) -> None:
    """Log static guidance and recognized codes, never arbitrary provider text."""
    code = "unclassified"
    error_type = "unclassified"
    status = None
    action = "Review validation checks in the originating component."
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        # SDK versions/providers may expose either the error object or envelope.
        body = exc.body
        if isinstance(body, dict):
            error = body.get("error", body)
            if isinstance(error, dict):
                candidate = error.get("code")
                if isinstance(candidate, str) and candidate in _PROVIDER_ACTIONS:
                    code = candidate
                candidate = error.get("type")
                if isinstance(candidate, str) and candidate in _PROVIDER_ACTIONS:
                    error_type = candidate
        action = _PROVIDER_ACTIONS.get(
            code if code != "unclassified" else error_type,
            {
                400: "Check model support for the request and structured-output schema.",
                401: "Check the server API key and its project permissions.",
                403: "Check API project permissions and model access.",
                404: "Check model availability and project access.",
                429: "Check API project quota, billing and rate limits.",
            }.get(status, "Check provider availability and API project configuration."),
        )
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        action = (
            "Check Ollama is running and the configured model is installed (ollama list)."
            if component.startswith("ollama.")
            else "Check provider availability and configuration."
        )
    elif isinstance(exc, (APITimeoutError, TimeoutError, httpx.TimeoutException)):
        action = "Check provider latency, network connectivity and request timeout."
    elif isinstance(exc, (APIConnectionError, httpx.RequestError)):
        action = (
            "Start Ollama and check VERICOMMIT_OLLAMA_BASE_URL."
            if component.startswith("ollama.")
            else "Check server network connectivity to the provider."
        )
    elif isinstance(exc, ValidationError):
        action = "Check structured response compatibility with the component schema."
    logger.error(
        "Evaluation failure component=%s exception=%s status=%s provider_code=%s provider_type=%s action=%s",
        component,
        type(exc).__name__,
        status,
        code,
        error_type,
        action,
    )
