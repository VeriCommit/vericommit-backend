"""HTTP contract integration tests with no live evidence or AI services."""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

from vericommit_backend.api.dependencies import get_evaluation_service
from vericommit_backend.config import Settings
from vericommit_backend.main import create_app
from vericommit_backend.schemas import (
    ErrorResponse,
    EvaluationRequest,
    EvaluationResponse,
)
from vericommit_backend.services.evaluation import EvaluationService

ENDPOINT = "/api/v1/evaluations"


@pytest.fixture
def payloads():
    contract = Path(__file__).resolve().parents[1] / "docs" / "API_CONTRACT.md"
    examples = re.findall(
        r"```json\s*(.*?)\s*```", contract.read_text(encoding="utf-8"), re.DOTALL
    )
    return json.loads(examples[0]), json.loads(examples[1])


@pytest.fixture
def application():
    return create_app(Settings(_env_file=None))


@pytest.fixture
def service(payloads):
    _, report = payloads
    service = AsyncMock(spec=EvaluationService)
    service.evaluate.return_value = EvaluationResponse.model_validate(report)
    return service


@pytest.fixture
def client(application, service):
    application.dependency_overrides[get_evaluation_service] = lambda: service
    with TestClient(application) as client:
        yield client
    application.dependency_overrides.clear()


def assert_error(response, status, code):
    assert response.status_code == status
    payload = response.json()
    assert ErrorResponse.model_validate(payload).model_dump() == payload
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "message"}
    assert payload["error"]["code"] == code
    assert payload["error"]["message"].strip()
    assert response.headers["content-type"] == "application/json"


@pytest.mark.parametrize("source", ["github", "sample"])
def test_valid_request_reaches_service_without_changing_contract(
    client, service, payloads, source
):
    request, report = payloads
    request["evidence_source"] = source
    criteria = [" First  ", "Second\ncriterion", " First  "]
    request["milestone"]["acceptance_criteria"] = criteria
    for result, criterion in zip(report["criteria_results"], criteria, strict=True):
        result["criterion"] = criterion
    if source == "sample":
        report["criteria_results"][0]["evidence"][0].update(
            title="Sample: registration form (illustrative)", url=None
        )
        report["limitations"].append("Sample evidence only; no live retrieval.")
    service.evaluate.return_value = EvaluationResponse.model_validate(report)

    response = client.post(ENDPOINT, json=request)

    assert response.status_code == 200
    assert response.json() == report
    assert response.json()["human_review_required"] is True
    service.evaluate.assert_awaited_once_with(EvaluationRequest.model_validate(request))


@pytest.mark.parametrize("source", ["github", "sample"])
def test_default_service_never_fabricates_a_success(application, payloads, source):
    request, _ = payloads
    request["evidence_source"] = source
    with TestClient(application) as client:
        response = client.post(ENDPOINT, json=request)
        assert client.get("/health").status_code == 200
    assert_error(response, 502, "EVALUATION_FAILED")
    assert response.json()["error"]["message"] == (
        "The evaluation service is not configured. No evaluation was performed."
    )


@pytest.mark.parametrize(
    "path",
    [
        ("project_name",),
        ("repository_url",),
        ("milestone",),
        ("evidence_source",),
        ("milestone", "title"),
        ("milestone", "description"),
        ("milestone", "acceptance_criteria"),
    ],
)
def test_missing_fields_stop_before_evaluation(client, service, payloads, path):
    request, _ = payloads
    parent = request if len(path) == 1 else request[path[0]]
    del parent[path[-1]]
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("project_name",), "  "),
        (("project_name",), None),
        (("project_name",), 123),
        (("repository_url",), None),
        (("repository_url",), 123),
        (("milestone",), None),
        (("milestone",), []),
        (("milestone", "title"), "\t"),
        (("milestone", "description"), ""),
        (("milestone", "acceptance_criteria"), []),
        (("milestone", "acceptance_criteria"), None),
        (("milestone", "acceptance_criteria"), [" "]),
        (("milestone", "acceptance_criteria"), ["Valid", ""]),
        (("milestone", "acceptance_criteria"), [42]),
        (("milestone", "acceptance_criteria"), "A criterion"),
    ],
)
def test_invalid_fields_stop_before_evaluation(client, service, payloads, path, value):
    request, _ = payloads
    parent = request if len(path) == 1 else request[path[0]]
    parent[path[-1]] = value
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


@pytest.mark.parametrize("source", ["other", "GitHub", "", None, 1])
def test_unsupported_source_is_standardized(client, service, payloads, source):
    request, _ = payloads
    request["evidence_source"] = source
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


@pytest.mark.parametrize("source", ["github", "sample"])
@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        " ",
        "http://github.com/example/repo",
        "https://example.org/owner/repo",
        "https://github.com/example",
        "https://github.com/example/repo/commits",
        "https://github.com/example/repo?token=do-not-echo",
        "https://user:do-not-echo@github.com/example/repo",
    ],
)
def test_repository_url_uses_specific_code_in_both_modes(
    client, service, payloads, source, url
):
    request, _ = payloads
    request.update(repository_url=url, evidence_source=source)
    response = client.post(ENDPOINT, json=request)
    assert_error(response, 400, "INVALID_REPOSITORY_URL")
    assert "do-not-echo" not in response.text
    service.evaluate.assert_not_awaited()


def test_specific_url_error_wins_over_generic_validation(client, service, payloads):
    request, _ = payloads
    request.update(repository_url="not-a-url", evidence_source="unsupported")
    del request["project_name"]
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REPOSITORY_URL")
    service.evaluate.assert_not_awaited()


def test_accepted_url_is_not_normalized(client, service, payloads):
    request, _ = payloads
    request["repository_url"] = "https://GITHUB.COM/example/repo/"
    assert client.post(ENDPOINT, json=request).status_code == 200
    assert (
        service.evaluate.call_args.args[0].repository_url == request["repository_url"]
    )


@pytest.mark.parametrize("source", ["github", "sample"])
def test_sample_also_requires_repository_url(client, service, payloads, source):
    request, _ = payloads
    request["evidence_source"] = source
    del request["repository_url"]
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "grantor_id"),
        ((), "grantee_id"),
        ((), "funding_agreement_id"),
        ((), "milestone_id"),
        (("milestone",), "id"),
        (("milestone",), "funding_agreement_id"),
    ],
)
def test_undocumented_relationship_fields_are_rejected(
    client, service, payloads, path, field
):
    request, _ = payloads
    parent = request[path[0]] if path else request
    parent[field] = "unapproved-id"
    assert_error(client.post(ENDPOINT, json=request), 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [b"", b"{", b'{"project_name":NaN}', b"null", b"[]", b'"text"', b"\xff"],
)
def test_missing_or_malformed_body_is_standardized(client, service, body):
    response = client.post(
        ENDPOINT, content=body, headers={"Content-Type": "application/json"}
    )
    assert_error(response, 400, "INVALID_REQUEST")
    service.evaluate.assert_not_awaited()


def test_response_validation_preserves_mandatory_human_review(
    client, service, payloads
):
    request, report = payloads
    report["human_review_required"] = False
    service.evaluate.return_value = report
    with pytest.raises(ResponseValidationError):
        client.post(ENDPOINT, json=request)


def test_openapi_uses_existing_models_and_http_400(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][ENDPOINT]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EvaluationRequest"
    }
    responses = operation["responses"]
    assert "422" not in responses
    for status in ("400", "502"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EvaluationResponse"
    }
