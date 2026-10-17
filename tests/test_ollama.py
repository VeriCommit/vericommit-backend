"""Native Ollama HTTP through the full endpoint; inference is mocked here."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from vericommit_backend.api import dependencies
from vericommit_backend.config import Settings
from vericommit_backend.main import create_app
from vericommit_backend.schemas import EvaluationResponse
from vericommit_backend.services.ai import CriterionAssessment
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


@pytest.fixture
def ollama_app(monkeypatch):
    http_factory = httpx.AsyncClient

    def make(handler):
        def factory(**kwargs):
            assert kwargs["base_url"] == "http://127.0.0.1:11434/"
            assert kwargs["timeout"] == 120
            assert kwargs["trust_env"] is False
            return http_factory(**kwargs, transport=httpx.MockTransport(handler))

        def forbidden(**kwargs):
            pytest.fail("Ollama must never construct a hosted provider or fallback")

        monkeypatch.setattr(dependencies, "httpx", SimpleNamespace(AsyncClient=factory))
        monkeypatch.setattr(dependencies, "AsyncOpenAI", forbidden)
        return create_app(
            Settings(
                _env_file=None,
                ai_provider="ollama",
                ollama_model="test-local-model",
                VERICOMMIT_OPENAI_API_KEY="",
                VERICOMMIT_GROQ_API_KEY="",
            )
        )

    return make


def chat_response(payload):
    return {
        "model": "test-local-model",
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": json.dumps(payload)},
        "eval_count": 100,
    }


def test_ollama_full_sample_endpoint_without_hosted_key(
    ai_request, assessment_payload, retrieved_evidence, ollama_app, caplog
):
    calls = []
    statuses = ["supported", "insufficient_evidence", "uncertain"]

    def handler(request):
        assert request.url.path == "/api/chat"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["model"] == "test-local-model"
        assert body["stream"] is False
        assert body["format"] == CriterionAssessment.model_json_schema()
        assert body["options"]["temperature"] == 0
        assert body["options"]["num_predict"] == 2000
        assert "UNTRUSTED DATA" in body["messages"][0]["content"]
        assert "Return JSON matching this schema:" in body["messages"][0]["content"]
        data = json.loads(body["messages"][1]["content"])
        assert "acceptance_criteria" not in data["milestone"]
        assert "repository_url" not in data
        assert all(
            "metadata" not in record and "url" not in record
            for record in data["evidence"]
        )
        calls.append(data["criterion"])
        return httpx.Response(
            200,
            json=chat_response(
                assessment_payload(data["criterion"], statuses[len(calls) - 1])
            ),
        )

    with caplog.at_level("DEBUG"), TestClient(ollama_app(handler)) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 200
    report = EvaluationResponse.model_validate(response.json())
    assert report.human_review_required is True
    assert calls == ai_request.milestone.acceptance_criteria
    assert [result.status for result in report.criteria_results] == statuses
    references = [
        record.to_public_reference() for record in retrieved_evidence.evidence
    ]
    assert all(
        ref in references
        for result in report.criteria_results
        for ref in result.evidence
    )
    assert report.suggested_next_steps
    assert "private-" not in caplog.text
    assert ai_request.milestone.description not in caplog.text
    assert retrieved_evidence.evidence[0].content not in caplog.text


@pytest.mark.parametrize(
    "failure", [400, 404, 429, 500, "connection", "timeout", "redirect"]
)
def test_ollama_provider_failures_are_safe_and_never_fallback(
    failure, ai_request, ollama_app, caplog
):
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "connection":
            raise httpx.ConnectError("private-network-detail", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-timeout", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "http://private-host"})
        return httpx.Response(failure, json={"error": "private-provider-detail"})

    with caplog.at_level("DEBUG"), TestClient(ollama_app(handler)) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == (504 if failure == "timeout" else 502)
    assert response.json()["error"]["code"] == "EVALUATION_FAILED"
    assert len(calls) == 1
    assert "component=ollama.api.chat" in caplog.text
    if failure == "connection":
        assert "Start Ollama and check VERICOMMIT_OLLAMA_BASE_URL." in caplog.text
    elif failure == 404:
        assert "status=404" in caplog.text
        assert "ollama list" in caplog.text
    assert "private-" not in response.text
    assert "private-" not in caplog.text
    assert ai_request.milestone.description not in caplog.text


@pytest.mark.parametrize(
    "defect",
    [
        "not_json",
        "outer_list",
        "missing_message",
        "wrong_role",
        "missing_content",
        "incomplete",
        "numeric_done",
        "truncated",
        "missing_done_reason",
        "tool_calls",
        "invalid_json",
        "fenced_json",
        "invalid_status",
        "extra_field",
        "blank_reasoning",
        "invented_id",
        "mismatched_quote",
        "missing_citations",
        "changed_criterion",
        "unsupported_claim",
        "invented_reference",
    ],
)
def test_ollama_bad_responses_and_grounding_rejections_never_produce_report(
    defect, ai_request, assessment_payload, ollama_app, caplog
):
    payload = assessment_payload(ai_request.milestone.acceptance_criteria[0])
    if defect == "invalid_status":
        payload["status"] = "approved"
    elif defect == "extra_field":
        payload["human_review_required"] = False
    elif defect == "blank_reasoning":
        payload["reasoning"] = " "
    elif defect == "invented_id":
        payload["citations"][0]["evidence_id"] = "sample:private:invented"
    elif defect == "mismatched_quote":
        payload["citations"][0]["quote"] = "private-invented-excerpt"
    elif defect == "missing_citations":
        payload["citations"] = []
    elif defect == "changed_criterion":
        payload["criterion"] += " changed"
    elif defect == "unsupported_claim":
        payload["reasoning"] = "I independently verified the registration behavior."
    elif defect == "invented_reference":
        payload["reasoning"] = "The changes in src/private.py support the criterion."
    output = chat_response(payload)
    if defect == "outer_list":
        output = []
    elif defect == "missing_message":
        del output["message"]
    elif defect == "wrong_role":
        output["message"]["role"] = "user"
    elif defect == "missing_content":
        del output["message"]["content"]
    elif defect == "incomplete":
        output["done"] = False
    elif defect == "numeric_done":
        output["done"] = 1
    elif defect == "truncated":
        output["done_reason"] = "length"
    elif defect == "missing_done_reason":
        del output["done_reason"]
    elif defect == "tool_calls":
        output["message"]["tool_calls"] = [{"function": {"name": "private-tool"}}]
    elif defect == "invalid_json":
        output["message"]["content"] = "private-not-json"
    elif defect == "fenced_json":
        output["message"]["content"] = (
            "```json\n" + output["message"]["content"] + "\n```"
        )
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(200, content=b"private-not-json")
            if defect == "not_json"
            else httpx.Response(200, json=output)
        )

    with caplog.at_level("DEBUG"), TestClient(ollama_app(handler)) as client:
        response = client.post(
            "/api/v1/evaluations", json=ai_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "EVALUATION_FAILED",
            "message": "AI evaluation or evidence grounding failed. No report was generated.",
        }
    }
    assert len(calls) == 1
    assert "private" not in caplog.text
    assert (
        "component=ollama.structured_response" in caplog.text
        or "component=grounding.validate_assessment" in caplog.text
    )
    assert (
        SampleEvidenceProvider().load_dataset().evidence[0].content not in caplog.text
    )
