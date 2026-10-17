"""Explicit selection, configuration and optional hosted provider integration."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import ValidationError

from vericommit_backend.api import dependencies
from vericommit_backend.config import Settings
from vericommit_backend.main import create_app
from vericommit_backend.schemas import EvaluationResponse
from vericommit_backend.services.ai import OpenAICriterionClient
from vericommit_backend.services.ollama import OllamaCriterionClient


def test_provider_settings_from_environment_and_secret_exclusion(monkeypatch):
    monkeypatch.setenv("VERICOMMIT_AI_PROVIDER", "ollama")
    monkeypatch.setenv("VERICOMMIT_OLLAMA_BASE_URL", "http://localhost:11434/proxy/")
    monkeypatch.setenv("VERICOMMIT_OLLAMA_MODEL", "a-local-model:small")
    monkeypatch.setenv("VERICOMMIT_OLLAMA_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("GROQ_API_KEY", "private-groq-key")
    settings = Settings(_env_file=None)
    assert settings.ai_provider == "ollama"
    assert settings.ollama_base_url == "http://localhost:11434/proxy"
    assert settings.ollama_model == "a-local-model:small"
    assert settings.evaluation_timeout_seconds == 180
    assert settings.groq_api_key.get_secret_value() == "private-groq-key"
    assert "private-groq-key" not in repr(settings)
    assert "groq_api_key" not in settings.model_dump()
    monkeypatch.setenv("VERICOMMIT_GROQ_API_KEY", "preferred-private-key")
    assert (
        Settings(_env_file=None).groq_api_key.get_secret_value()
        == "preferred-private-key"
    )
    assert Settings(_env_file=None, VERICOMMIT_GROQ_API_KEY=" ").groq_api_key is None
    assert Settings(_env_file=None, groq_model=" ").groq_model is None


@pytest.mark.parametrize(
    "invalid",
    [
        {"ai_provider": "mock"},
        {"ollama_model": " "},
        {"ollama_timeout_seconds": 0},
        {"ollama_timeout_seconds": 301},
        {"ollama_timeout_seconds": float("nan")},
        {"ollama_base_url": "file:///private"},
        {"ollama_base_url": "http://user:private@localhost:11434"},
        {"ollama_base_url": "http://localhost:11434?api_key=private"},
        {"ollama_base_url": "http://localhost:11434#private"},
        {"ollama_base_url": "http://localhost:99999"},
        {"ollama_base_url": "http://local host"},
        {"groq_model": 123},
    ],
)
def test_invalid_provider_configuration_is_rejected(invalid):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **invalid)


@pytest.mark.parametrize("provider", ["openai", "ollama", "groq"])
def test_only_selected_provider_is_created_and_closed(provider, monkeypatch):
    created = []
    http_factory = httpx.AsyncClient
    clients = []

    def local_factory(**kwargs):
        assert provider == "ollama"
        assert kwargs["timeout"] == 150
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        client = http_factory(**kwargs)
        clients.append(client)
        created.append("ollama")
        return client

    def sdk_factory(**kwargs):
        assert provider != "ollama"
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == 30
        expected_key = "openai-test" if provider == "openai" else "groq-test"
        assert kwargs["api_key"] == expected_key
        if provider == "groq":
            assert kwargs["base_url"] == "https://api.groq.com/openai/v1"
        client = AsyncOpenAI(**kwargs, http_client=http_factory())
        clients.append(client)
        created.append(provider)
        return client

    monkeypatch.setattr(
        dependencies, "httpx", SimpleNamespace(AsyncClient=local_factory)
    )
    monkeypatch.setattr(dependencies, "AsyncOpenAI", sdk_factory)
    settings = Settings(
        _env_file=None,
        ai_provider=provider,
        VERICOMMIT_OPENAI_API_KEY="openai-test",
        VERICOMMIT_GROQ_API_KEY="groq-test",
        groq_model="configured-strict-model",
        ollama_timeout_seconds=150,
    )

    # FastAPI consumes the dependency's async generator, including its cleanup.
    async def consume():
        generator = dependencies.get_ai_client(settings)
        client = await anext(generator)
        expected = (
            OllamaCriterionClient if provider == "ollama" else OpenAICriterionClient
        )
        assert isinstance(client, expected)
        service = dependencies.get_evaluation_service(object(), client, settings)
        assert service.timeout_seconds == (150 if provider == "ollama" else 30)
        await generator.aclose()

    asyncio.run(consume())
    assert created == [provider]
    assert all(
        client.is_closed() if isinstance(client, AsyncOpenAI) else client.is_closed
        for client in clients
    )


@pytest.mark.parametrize(
    ("provider", "key", "model"),
    [
        ("groq", "", "configured-model"),
        ("groq", "test-key", None),
        ("openai", "", None),
    ],
)
def test_missing_selected_provider_configuration_never_uses_other_provider(
    provider, key, model, ai_request, monkeypatch
):
    def forbidden(**kwargs):
        pytest.fail("Missing configuration must not construct any provider")

    monkeypatch.setattr(dependencies, "AsyncOpenAI", forbidden)
    monkeypatch.setattr(dependencies, "httpx", SimpleNamespace(AsyncClient=forbidden))
    settings = Settings(
        _env_file=None,
        ai_provider=provider,
        VERICOMMIT_OPENAI_API_KEY=key
        if provider == "openai"
        else "available-openai-key",
        VERICOMMIT_GROQ_API_KEY=key,
        groq_model=model,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert response.json()["error"]["message"].startswith(
        "The evaluation service is not configured."
    )


@pytest.mark.parametrize(
    "failure",
    [
        None,
        401,
        429,
        500,
        "timeout",
        "malformed",
        "invalid_status",
        "invented_id",
        "mismatched_quote",
        "unsupported_claim",
        "truncated",
        "refusal",
    ],
)
def test_groq_complete_endpoint_with_mocked_upstream(
    failure, ai_request, assessment_payload, monkeypatch, caplog
):
    seen = []

    def handler(request):
        assert request.url.host == "api.groq.com"
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer private-groq-key"
        body = json.loads(request.content)
        assert body["model"] == "explicitly-configured-model"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert "store" not in body
        data = json.loads(body["messages"][1]["content"])
        seen.append(data["criterion"])
        if isinstance(failure, int):
            return httpx.Response(failure, json={"error": {"message": "private-body"}})
        if failure == "timeout":
            raise httpx.ReadTimeout("private-timeout", request=request)
        output = assessment_payload(data["criterion"])
        if failure == "invalid_status":
            output["status"] = "approved"
        elif failure == "invented_id":
            output["citations"][0]["evidence_id"] = "sample:private:invented"
        elif failure == "mismatched_quote":
            output["citations"][0]["quote"] = "private-invented-excerpt"
        elif failure == "unsupported_claim":
            output["reasoning"] = "I independently verified the registration behavior."
        return httpx.Response(
            200,
            json={
                "id": "mock-groq",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length" if failure == "truncated" else "stop",
                        "message": {
                            "role": "assistant",
                            "refusal": "private-refusal"
                            if failure == "refusal"
                            else None,
                            "content": "bad JSON"
                            if failure == "malformed"
                            else json.dumps(output),
                        },
                    }
                ],
            },
        )

    def sdk_factory(**kwargs):
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(dependencies, "AsyncOpenAI", sdk_factory)
    settings = Settings(
        _env_file=None,
        ai_provider="groq",
        VERICOMMIT_GROQ_API_KEY="private-groq-key",
        groq_model="explicitly-configured-model",
    )
    with caplog.at_level("DEBUG"), TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    if failure is None:
        assert response.status_code == 200
        report = EvaluationResponse.model_validate(response.json())
        assert report.human_review_required is True
        assert seen == ai_request.milestone.acceptance_criteria
    else:
        assert response.status_code == (504 if failure == "timeout" else 502)
        assert response.json()["error"]["code"] == "EVALUATION_FAILED"
        assert len(seen) == 1
        assert (
            "component=groq." in caplog.text
            or "component=grounding.validate_assessment" in caplog.text
        )
    assert "private-" not in caplog.text
    assert ai_request.milestone.description not in caplog.text
