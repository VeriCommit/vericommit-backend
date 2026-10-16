"""Real SDK adapter exercised with mocked HTTP, never credentials or live AI."""

import asyncio
import json
import logging

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import ValidationError

from vericommit_backend.config import Settings
from vericommit_backend.services.ai import (
    AIEvaluationError,
    AITimeoutError,
    CriterionAssessment,
    OpenAICriterionClient,
)


def completion(content, finish_reason="stop", refusal=None):
    return {
        "id": "test-completion",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "refusal": refusal,
                },
            }
        ],
    }


def test_sdk_uses_structured_single_criterion_input(
    ai_request, retrieved_evidence, assessment_payload
):
    criterion = ai_request.milestone.acceptance_criteria[0]
    payload = assessment_payload(criterion)
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json=completion(json.dumps(payload)))

    async def run():
        async with AsyncOpenAI(
            api_key="test-only",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as sdk:
            return await OpenAICriterionClient(sdk, "test-model").assess(
                criterion, ai_request.milestone, retrieved_evidence
            )

    assert asyncio.run(run()) == CriterionAssessment.model_validate(payload)
    assert len(seen) == 1
    sent = seen[0]
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["store"] is False
    assert sent["messages"][0]["role"] == "system"
    assert "UNTRUSTED DATA" in sent["messages"][0]["content"]
    data = json.loads(sent["messages"][1]["content"])
    assert data["criterion"] == criterion
    assert "acceptance_criteria" not in data["milestone"]
    assert "repository_url" not in data
    assert all(
        "url" not in item and "metadata" not in item for item in data["evidence"]
    )


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_errors_fail_without_retry_or_leaking_details(
    ai_request, retrieved_evidence, status, caplog
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": {"message": "private-provider-detail"}}
        )

    async def run():
        async with AsyncOpenAI(
            api_key="test-only",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as sdk:
            await OpenAICriterionClient(sdk, "test-model").assess(
                ai_request.milestone.acceptance_criteria[0],
                ai_request.milestone,
                retrieved_evidence,
            )

    with pytest.raises(AIEvaluationError) as exc_info:
        asyncio.run(run())
    assert len(calls) == 1
    assert "private-provider-detail" not in str(exc_info.value)
    assert "test-only" not in caplog.text


def test_sdk_timeout_is_explicit(ai_request, retrieved_evidence):
    def handler(request):
        raise httpx.ReadTimeout("private timeout detail", request=request)

    async def run():
        async with AsyncOpenAI(
            api_key="test-only",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as sdk:
            await OpenAICriterionClient(sdk, "test-model").assess(
                ai_request.milestone.acceptance_criteria[0],
                ai_request.milestone,
                retrieved_evidence,
            )

    with pytest.raises(AITimeoutError):
        asyncio.run(run())


@pytest.mark.parametrize(
    "variant", ["json", "status", "extra", "missing", "truncated", "refusal"]
)
def test_bad_ai_output_fails_explicitly(
    ai_request, retrieved_evidence, assessment_payload, variant
):
    payload = assessment_payload(ai_request.milestone.acceptance_criteria[0])
    if variant == "status":
        payload["status"] = "approved"
    if variant == "extra":
        payload["human_review_required"] = False
    if variant == "missing":
        del payload["reasoning"]
    response = completion(
        "not json" if variant == "json" else json.dumps(payload),
        finish_reason="length" if variant == "truncated" else "stop",
        refusal="Cannot comply" if variant == "refusal" else None,
    )

    async def run():
        async with AsyncOpenAI(
            api_key="test-only",
            max_retries=0,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=response)
                )
            ),
        ) as sdk:
            await OpenAICriterionClient(sdk, "test-model").assess(
                ai_request.milestone.acceptance_criteria[0],
                ai_request.milestone,
                retrieved_evidence,
            )

    with pytest.raises(AIEvaluationError):
        asyncio.run(run())


def test_credentials_are_excluded_and_settings_validated(monkeypatch):
    monkeypatch.setenv("VERICOMMIT_OPENAI_API_KEY", "test-secret-not-a-real-key")
    settings = Settings(_env_file=None)
    assert settings.openai_api_key.get_secret_value() == "test-secret-not-a-real-key"
    assert "test-secret" not in repr(settings)
    assert "openai_api_key" not in settings.model_dump()
    assert Settings(_env_file=None, VERICOMMIT_OPENAI_API_KEY="").openai_api_key is None
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ai_timeout_seconds=0)


@pytest.mark.parametrize("status", [200, 401, 500])
def test_sdk_debug_logs_never_disclose_source_or_credentials(
    ai_request, retrieved_evidence, assessment_payload, caplog, status
):
    criterion = ai_request.milestone.acceptance_criteria[0]
    payload = assessment_payload(criterion)

    def handler(request):
        if status == 200:
            return httpx.Response(200, json=completion(json.dumps(payload)))
        return httpx.Response(
            status, json={"error": {"message": "confidential-provider-body"}}
        )

    async def run():
        async with AsyncOpenAI(
            api_key="private-key-sentinel",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ) as sdk:
            client = OpenAICriterionClient(sdk, "test-model")
            if status == 200:
                await client.assess(criterion, ai_request.milestone, retrieved_evidence)
            else:
                with pytest.raises(AIEvaluationError):
                    await client.assess(
                        criterion, ai_request.milestone, retrieved_evidence
                    )

    with caplog.at_level(logging.DEBUG, logger="openai._base_client"):
        asyncio.run(run())
    assert "private-key-sentinel" not in caplog.text
    assert "confidential-provider-body" not in caplog.text
    assert criterion not in caplog.text
    assert retrieved_evidence.evidence[0].content not in caplog.text
    assert not any(r.name == "openai._base_client" for r in caplog.records)
