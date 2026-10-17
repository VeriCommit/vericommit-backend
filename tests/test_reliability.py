"""CORS and safe failures through the public endpoint, including unexpected bugs."""

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vericommit_backend.api.dependencies import get_evaluation_service
from vericommit_backend.config import Settings
from vericommit_backend.evidence.providers import (
    EvidenceProviderError,
    EvidenceRateLimitError,
    EvidenceTimeoutError,
    RepositoryAccessDeniedError,
)
from vericommit_backend.main import create_app
from vericommit_backend.services.ai import AIEvaluationError, AITimeoutError

ENDPOINT = "/api/v1/evaluations"
ORIGIN = "http://localhost:3000"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_browser_preflight_supports_required_methods_and_headers(method):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.options(
            ENDPOINT,
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type, accept",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert method in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(
    "origin,method,header",
    [
        ("https://untrusted.example", "POST", "content-type"),
        (ORIGIN, "DELETE", "content-type"),
        (ORIGIN, "POST", "x-unapproved-header"),
    ],
)
def test_unapproved_preflights_are_rejected(origin, method, header):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.options(
            ENDPOINT,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": header,
            },
        )
    assert response.status_code == 400
    if origin != ORIGIN:
        assert "access-control-allow-origin" not in response.headers


def test_cors_environment_is_explicit_and_can_deny_all(monkeypatch):
    monkeypatch.setenv("VERICOMMIT_CORS_ORIGINS", '["https://demo.example/"]')
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://demo.example"]
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/health", headers={"Origin": "https://demo.example"}).headers[
                "access-control-allow-origin"
            ]
            == "https://demo.example"
        )
        assert (
            "access-control-allow-origin"
            not in client.get("/health", headers={"Origin": ORIGIN}).headers
        )
    with TestClient(create_app(Settings(_env_file=None, cors_origins=[]))) as client:
        assert (
            "access-control-allow-origin"
            not in client.get("/health", headers={"Origin": ORIGIN}).headers
        )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example",
        "https://user:private@example.com",
        "https://example.com/path",
        "https://example.com?private=1",
        "https://example.com#fragment",
        "file:///tmp",
        "https://example.com:99999",
    ],
)
def test_invalid_or_wildcard_cors_configuration_is_rejected(origin):
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, cors_origins=[origin])
    assert "private" not in str(exc_info.value)


@pytest.mark.parametrize(
    "exc,status,code",
    [
        (RepositoryAccessDeniedError("private body"), 403, "REPOSITORY_ACCESS_DENIED"),
        (EvidenceProviderError("private body"), 502, "EVIDENCE_RETRIEVAL_FAILED"),
        (EvidenceRateLimitError("private body"), 502, "EVIDENCE_RETRIEVAL_FAILED"),
        (EvidenceTimeoutError("private body"), 504, "EVIDENCE_RETRIEVAL_FAILED"),
        (AIEvaluationError("private body"), 502, "EVALUATION_FAILED"),
        (AITimeoutError("private body"), 504, "EVALUATION_FAILED"),
        (
            RuntimeError("Authorization: private-key; private evidence"),
            502,
            "EVALUATION_FAILED",
        ),
        (
            HTTPException(
                500, detail="private body", headers={"Authorization": "private-key"}
            ),
            502,
            "EVALUATION_FAILED",
        ),
    ],
)
def test_all_failures_have_safe_envelopes_cors_and_no_server_trace(
    exc, status, code, ai_request, caplog
):
    app = create_app(Settings(_env_file=None))
    service = AsyncMock()
    service.evaluate.side_effect = exc
    app.dependency_overrides[get_evaluation_service] = lambda: service
    # Default raise_server_exceptions=True proves no exception escapes to Uvicorn.
    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        response = client.post(
            ENDPOINT,
            json=ai_request.model_dump(mode="json"),
            headers={"Origin": ORIGIN},
        )
    assert response.status_code == status
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}
    assert response.json()["error"]["code"] == code
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "private" not in response.text + caplog.text + str(dict(response.headers))
    assert "Traceback" not in caplog.text


def test_validation_failure_has_cors_and_no_submitted_values():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post(
            ENDPOINT,
            json={"repository_url": "http://private-token@localhost/repo"},
            headers={"Origin": ORIGIN},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REPOSITORY_URL"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "private-token" not in response.text


def test_verbose_transport_and_asgi_logs_cannot_disclose_data(caplog):
    create_app(Settings(_env_file=None))
    with caplog.at_level(logging.DEBUG):
        for name in (
            "openai._base_client",
            "httpx",
            "httpcore.http11",
            "uvicorn.asgi",
            "uvicorn.access",
        ):
            logging.getLogger(name).error(
                "Authorization: private-key; private evidence"
            )
    assert "private" not in caplog.text
