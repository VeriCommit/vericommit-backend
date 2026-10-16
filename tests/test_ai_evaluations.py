"""End-to-end application evaluation with a mocked AI upstream, not a live demo."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from vericommit_backend.api import dependencies
from vericommit_backend.api.dependencies import get_ai_client, get_evidence_provider
from vericommit_backend.config import Settings
from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.evidence.providers import (
    EvidenceProvider,
    EvidenceProviderError,
)
from vericommit_backend.main import create_app
from vericommit_backend.schemas import EvaluationResponse
from vericommit_backend.services.ai import (
    AIEvaluationError,
    AITimeoutError,
    CriterionAIClient,
    CriterionAssessment,
)
from vericommit_backend.services.evaluation import AIEvaluationService
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def test_configured_endpoint_real_sdk_and_services_with_mocked_upstream(
    ai_request, assessment_payload, monkeypatch
):
    seen = []
    statuses = ["supported", "insufficient_evidence", "uncertain"]

    def handler(request):
        body = json.loads(request.content)
        data = json.loads(body["messages"][1]["content"])
        status = statuses[len(seen) % 3]
        seen.append(data["criterion"])
        output = assessment_payload(data["criterion"], status)
        return httpx.Response(
            200,
            json={
                "id": "mock-upstream",
                "created": 0,
                "object": "chat.completion",
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(output)},
                    }
                ],
            },
        )

    def sdk_factory(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == 30
        return AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(dependencies, "AsyncOpenAI", sdk_factory)
    app = create_app(
        Settings(
            _env_file=None, VERICOMMIT_OPENAI_API_KEY="test-only", ai_model="test-model"
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
        second = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == second.status_code == 200
    report = response.json()
    assert EvaluationResponse.model_validate(report).model_dump(mode="json") == report
    assert set(report) == set(EvaluationResponse.model_fields)
    assert [result["status"] for result in report["criteria_results"]] == statuses
    assert seen == ai_request.milestone.acceptance_criteria * 2
    assert report["evaluation_id"] != second.json()["evaluation_id"]
    assert report["project_name"] == ai_request.project_name
    assert report["milestone_title"] == ai_request.milestone.title
    assert report["human_review_required"] is True
    assert "uncertain" in report["overall_summary"]
    assert any("synthetic" in item for item in report["limitations"])
    assert report["suggested_next_steps"]
    for result in report["criteria_results"]:
        for evidence in result["evidence"]:
            assert set(evidence) == {"type", "title", "url"}
            assert evidence["url"] is None
            assert evidence["title"].startswith("Sample: ")


def test_original_order_whitespace_and_duplicates_are_evaluated_independently(
    ai_request, assessment_payload
):
    criteria = [" Same criterion  ", "Another criterion", " Same criterion  "]
    ai_request.milestone.acceptance_criteria = criteria
    ai = AsyncMock(spec=CriterionAIClient)
    ai.assess.side_effect = [
        CriterionAssessment.model_validate(assessment_payload(c)) for c in criteria
    ]
    report = asyncio.run(
        AIEvaluationService(SampleEvidenceProvider(), ai).evaluate(ai_request)
    )
    assert [result.criterion for result in report.criteria_results] == criteria
    assert [call.args[0] for call in ai.assess.await_args_list] == criteria


@pytest.mark.parametrize("failure", ["provider", "timeout", "grounding"])
def test_ai_failures_return_approved_error_and_no_partial_report(
    ai_request, assessment_payload, failure
):
    ai = AsyncMock(spec=CriterionAIClient)
    if failure == "grounding":
        payload = assessment_payload(ai_request.milestone.acceptance_criteria[0])
        payload["citations"][0]["evidence_id"] = "sample:invented:record"
        ai.assess.return_value = CriterionAssessment.model_validate(payload)
    else:
        ai.assess.side_effect = (
            AITimeoutError("private")
            if failure == "timeout"
            else AIEvaluationError("private")
        )
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == (504 if failure == "timeout" else 502)
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message"}
    assert response.json()["error"]["code"] == "EVALUATION_FAILED"
    assert "private" not in response.text
    assert ai.assess.await_count == 1


def test_retrieval_failure_stops_ai_before_any_evaluation(ai_request):
    provider = AsyncMock(spec=EvidenceProvider)
    provider.retrieve.side_effect = EvidenceProviderError("private fixture detail")
    ai = AsyncMock(spec=CriterionAIClient)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    app.dependency_overrides[get_evidence_provider] = lambda: provider
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EVIDENCE_RETRIEVAL_FAILED"
    assert "private fixture detail" not in response.text
    ai.assess.assert_not_awaited()


def test_empty_successful_retrieval_can_return_honest_insufficient_report(
    ai_request, assessment_payload
):
    provider = AsyncMock(spec=EvidenceProvider)
    provider.retrieve.return_value = EvidenceCollection(
        source="sample", evidence=(), limitations=("No evidence available.",)
    )
    ai = AsyncMock(spec=CriterionAIClient)
    ai.assess.side_effect = [
        CriterionAssessment.model_validate(
            assessment_payload(c, "insufficient_evidence")
        )
        for c in ai_request.milestone.acceptance_criteria
    ]
    report = asyncio.run(AIEvaluationService(provider, ai).evaluate(ai_request))
    assert all(
        result.status == "insufficient_evidence" for result in report.criteria_results
    )
    assert all(
        "does not establish that work was not performed" in result.explanation
        for result in report.criteria_results
    )
    assert "0 supported" in report.overall_summary


def test_github_mode_is_explicitly_unsupported_without_sample_fallback(ai_request):
    ai_request.evidence_source = "github"
    ai = AsyncMock(spec=CriterionAIClient)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EVIDENCE_RETRIEVAL_FAILED"
    ai.assess.assert_not_awaited()


def test_orchestrator_enforces_timeout(ai_request):
    async def slow(*args):
        await asyncio.sleep(1)

    ai = AsyncMock(spec=CriterionAIClient)
    ai.assess.side_effect = slow
    with pytest.raises(AITimeoutError):
        asyncio.run(
            AIEvaluationService(
                SampleEvidenceProvider(), ai, timeout_seconds=0.001
            ).evaluate(ai_request)
        )


def test_missing_key_never_falls_back_to_mock(ai_request, monkeypatch):
    monkeypatch.delenv("VERICOMMIT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def forbidden_sdk(**kwargs):
        pytest.fail("No SDK should be constructed without a key")

    monkeypatch.setattr(dependencies, "AsyncOpenAI", forbidden_sdk)
    app = create_app(Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EVALUATION_FAILED"


def test_later_criterion_failure_never_returns_partial_success(
    ai_request, assessment_payload
):
    ai = AsyncMock(spec=CriterionAIClient)
    ai.assess.side_effect = [
        CriterionAssessment.model_validate(
            assessment_payload(ai_request.milestone.acceptance_criteria[0])
        ),
        AIEvaluationError("second criterion failed"),
    ]
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert set(response.json()) == {"error"}
    assert ai.assess.await_count == 2


def test_invalid_request_stops_configured_ai(ai_request):
    ai = AsyncMock(spec=CriterionAIClient)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    ai_request.milestone.acceptance_criteria = []
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 400
    ai.assess.assert_not_awaited()
