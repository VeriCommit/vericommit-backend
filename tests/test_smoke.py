"""Smoke commands use the real endpoint/services with mocked provider boundaries."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from examples import smoke_evaluation as smoke
from vericommit_backend.api.dependencies import get_ai_client, get_evidence_provider
from vericommit_backend.config import Settings
from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.evidence.normalization import normalize_github_commit
from vericommit_backend.main import create_app
from vericommit_backend.services.ai import CriterionAssessment
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


@pytest.fixture
def backend_transport():
    def make(source="sample", mutate=None):
        app = create_app(Settings(_env_file=None))
        if source == "sample":
            collection = SampleEvidenceProvider().load_dataset()
        else:
            collection = EvidenceCollection(
                source="github",
                evidence=(
                    normalize_github_commit(
                        "octocat/Hello-World",
                        {
                            "sha": "a" * 40,
                            "commit": {
                                "message": "Describe README updates and documented changes."
                            },
                            "html_url": "https://github.com/octocat/Hello-World/commit/"
                            + "a" * 40,
                        },
                    ),
                ),
                limitations=("Mocked public GitHub snapshot; not verified execution.",),
            )
        provider, ai = AsyncMock(), AsyncMock()
        provider.retrieve.return_value = collection
        calls = []

        async def assess(criterion, milestone, evidence):
            status = ["supported", "insufficient_evidence", "uncertain"][len(calls) % 3]
            calls.append(criterion)
            record = evidence.evidence[0]
            return CriterionAssessment.model_validate(
                {
                    "criterion": criterion,
                    "status": status,
                    "reasoning": "The supplied excerpt describes changes; execution is not independently verified.",
                    "citations": []
                    if status == "insufficient_evidence"
                    else [
                        {
                            "evidence_id": record.evidence_id,
                            "quote": record.content[:64],
                        }
                    ],
                    "uncertainties": []
                    if status == "supported"
                    else [
                        "Complete scenario coverage is not established by the supplied evidence."
                    ],
                    "suggested_next_steps": [
                        "Have a human reviewer inspect the evidence and test results."
                    ],
                }
            )

        ai.assess.side_effect = assess
        app.dependency_overrides[get_ai_client] = lambda: ai
        app.dependency_overrides[get_evidence_provider] = lambda: provider
        backend = TestClient(app)

        def handler(request):
            response = backend.request(
                request.method,
                str(request.url),
                content=request.content,
                headers=request.headers,
            )
            if response.status_code == 200 and request.method == "POST" and mutate:
                report = response.json()
                mutate(report)
                return httpx.Response(200, json=report, headers=response.headers)
            return httpx.Response(
                response.status_code, content=response.content, headers=response.headers
            )

        return httpx.MockTransport(handler), calls

    return make


@pytest.mark.parametrize("source", ["sample", "github"])
def test_smoke_verifies_public_endpoint_health_cors_and_report(
    source, backend_transport, capsys
):
    transport, calls = backend_transport(source)
    assert smoke.main(["--source", source, "--summary"], transport=transport) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["source"] == source
    assert (
        output["health"]
        == output["cors_preflight"]
        == output["invalid_request"]
        == "ok"
    )
    assert output["human_review_required"] is True
    fixture = json.loads(
        (smoke.FIXTURES / f"{source}_evaluation.json").read_text(encoding="utf-8")
    )
    assert calls == fixture["milestone"]["acceptance_criteria"]
    assert output["references"] > 0


@pytest.mark.parametrize(
    "defect",
    [
        "order",
        "source",
        "review",
        "missing_url",
        "foreign_reference",
        "no_citations",
        "project",
    ],
)
def test_smoke_rejects_invalid_or_untraceable_reports(
    defect, backend_transport, capsys
):
    def mutate(report):
        if defect == "order":
            report["criteria_results"].reverse()
        elif defect == "source":
            report["limitations"] = []
        elif defect == "review":
            report["human_review_required"] = False
        elif defect == "missing_url":
            del report["criteria_results"][0]["evidence"][0]["url"]
        elif defect == "foreign_reference":
            report["criteria_results"][0]["evidence"][0]["title"] = (
                "Unrelated fabricated source"
            )
        elif defect == "no_citations":
            report["criteria_results"][0]["evidence"] = []
        else:
            report["project_name"] = "Unrelated project"

    transport, _ = backend_transport(mutate=mutate)
    assert smoke.main(["--summary"], transport=transport) == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "failure", ["provider", "invalid_json", "timeout", "bad_preflight"]
)
def test_smoke_failures_are_sanitized_and_do_not_invent_reports(
    failure, backend_transport, capsys
):
    normal, _ = backend_transport()

    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("Authorization: private-key", request=request)
        if request.method == "OPTIONS" and failure == "bad_preflight":
            return httpx.Response(400, text="private-detail")
        if (
            request.method == "POST"
            and json.loads(request.content)["milestone"]["acceptance_criteria"]
        ):
            if failure == "provider":
                return httpx.Response(
                    502,
                    json={
                        "error": {
                            "code": "EVALUATION_FAILED",
                            "message": "private-key provider detail",
                        }
                    },
                )
            if failure == "invalid_json":
                return httpx.Response(200, text="private-key upstream body")
        return normal.handle_request(request)

    assert smoke.main(["--summary"], transport=httpx.MockTransport(handler)) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "private" not in captured.err
    assert "Traceback" not in captured.err


def test_invalid_demo_fixture_is_rejected_before_providers():
    fixture = (
        Path(__file__).parents[1] / "examples" / "invalid_evaluation.json"
    ).read_bytes()
    app = create_app(Settings(_env_file=None))
    ai = AsyncMock()
    app.dependency_overrides[get_ai_client] = lambda: ai
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations",
            content=fixture,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    ai.assess.assert_not_awaited()
