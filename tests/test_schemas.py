"""Contract-oriented tests; example data is illustrative, not verified evidence."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from vericommit_backend.schemas import (
    CriterionResult,
    ErrorResponse,
    EvaluationRequest,
    EvaluationResponse,
    EvidenceReference,
    Milestone,
)


@pytest.fixture(scope="module")
def contract_examples():
    contract = Path(__file__).resolve().parents[1] / "docs" / "API_CONTRACT.md"
    examples = re.findall(r"```json\s*(.*?)\s*```", contract.read_text(), re.DOTALL)
    assert len(examples) == 4
    return [json.loads(example) for example in examples]


@pytest.mark.parametrize(
    ("index", "model"),
    [(0, EvaluationRequest), (1, EvaluationResponse), (3, ErrorResponse)],
)
def test_published_contract_json_examples_round_trip(contract_examples, index, model):
    example = contract_examples[index]
    assert model.model_validate(example).model_dump(mode="json") == example


def test_approved_sample_evidence_example_round_trip(contract_examples):
    example = contract_examples[2]
    assert example["url"] is None
    assert EvidenceReference.model_validate(example).model_dump(mode="json") == example


@pytest.fixture
def request_data():
    return {
        "project_name": "Community Tools",
        "repository_url": "https://github.com/example/community-tools",
        "milestone": {
            "title": "Implement member registration",
            "description": "Allow a new member to register and access the application.",
            "acceptance_criteria": [
                "A user can submit the registration form.",
                "Invalid input produces understandable validation errors.",
                "Automated tests cover successful and unsuccessful registration.",
            ],
        },
        "evidence_source": "github",
    }


@pytest.fixture
def response_data():
    return {
        "evaluation_id": "eval_demo_001",
        "project_name": "Community Tools",
        "milestone_title": "Implement member registration",
        "overall_summary": "Some evidence supports progress, but not every criterion is shown.",
        "criteria_results": [
            {
                "criterion": "A user can submit the registration form.",
                "status": "supported",
                "explanation": "A pull request describes the form implementation.",
                "evidence": [
                    {
                        "type": "pull_request",
                        "title": "Add registration form",
                        "url": "https://github.com/example/community-tools/pull/12",
                    }
                ],
            },
            {
                "criterion": "Invalid input produces understandable validation errors.",
                "status": "insufficient_evidence",
                "explanation": "Available evidence does not demonstrate validation.",
                "evidence": [],
            },
            {
                "criterion": "Automated tests cover successful and unsuccessful registration.",
                "status": "uncertain",
                "explanation": "Test coverage remains unclear.",
                "evidence": [],
            },
        ],
        "suggested_next_steps": ["Review registration tests."],
        "limitations": ["Repository activity does not prove production behavior."],
        "human_review_required": True,
    }


@pytest.mark.parametrize("source", ["github", "sample"])
def test_request_preserves_documented_shape_and_sample_url(request_data, source):
    request_data["evidence_source"] = source
    request = EvaluationRequest.model_validate(request_data)
    assert request.model_dump(mode="json") == request_data
    assert request.repository_url == "https://github.com/example/community-tools"


@pytest.mark.parametrize(
    "field", ["project_name", "repository_url", "milestone", "evidence_source"]
)
def test_request_rejects_missing_fields(request_data, field):
    del request_data[field]
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("field", ["title", "description", "acceptance_criteria"])
def test_milestone_rejects_missing_fields(request_data, field):
    del request_data["milestone"][field]
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("field", ["title", "description"])
@pytest.mark.parametrize("value", ["", " \t\n"])
def test_milestone_rejects_blank_strings(request_data, field, value):
    request_data["milestone"][field] = value
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("field", ["project_name", "repository_url"])
def test_request_rejects_blank_strings(request_data, field):
    request_data[field] = "   "
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


def test_milestone_rejects_empty_criteria(request_data):
    request_data["milestone"]["acceptance_criteria"] = []
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("criteria", [[""], ["Valid", " \t"], [42]])
def test_milestone_rejects_blank_or_non_string_criteria(request_data, criteria):
    request_data["milestone"]["acceptance_criteria"] = criteria
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("source", ["other", "GitHub", "", None])
def test_rejects_unapproved_evidence_sources(request_data, source):
    request_data["evidence_source"] = source
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/example",
        "https://github.com/example/repo/commits",
        "https://github.com/-/repo",
        "https://github.com/example/..",
        "https://github.com/example/repo?token=test",
        "https://github.com/example/repo#fragment",
        "https://github.com/example/repo?",
        "https://github.com/example/repo#",
        "https://github.com/example/repo\n",
        "\x00https://github.com/example/repo",
        "https://github.com/example/repo name",
        "https://github.com:443/example/repo",
        "https://user@github.com/example/repo",
        "https://github.com.evil.test/example/repo",
        "http://github.com/example/repo",
        "file:///example/repo",
        "not-a-url",
    ],
)
@pytest.mark.parametrize("source", ["github", "sample"])
def test_invalid_repository_urls_rejected_in_both_modes(request_data, source, url):
    request_data.update(repository_url=url, evidence_source=source)
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


def test_repository_url_trailing_slash_retained(request_data):
    request_data["repository_url"] += "/"
    assert (
        EvaluationRequest.model_validate(request_data).repository_url
        == request_data["repository_url"]
    )


@pytest.mark.parametrize("source", ["github", "sample"])
def test_repository_url_is_required_in_both_modes(request_data, source):
    request_data["evidence_source"] = source
    del request_data["repository_url"]
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


@pytest.mark.parametrize("status", ["supported", "insufficient_evidence", "uncertain"])
def test_allowed_criterion_statuses(response_data, status):
    response_data["criteria_results"][0]["status"] = status
    result = EvaluationResponse.model_validate(response_data)
    assert result.criteria_results[0].status == status


@pytest.mark.parametrize("status", ["failed", "approved", "", None])
def test_invalid_criterion_statuses(response_data, status):
    response_data["criteria_results"][0]["status"] = status
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_evidence_reference_serialization(response_data):
    evidence_data = response_data["criteria_results"][0]["evidence"][0]
    assert (
        json.loads(EvidenceReference.model_validate(evidence_data).model_dump_json())
        == evidence_data
    )


def test_sample_evidence_null_url_is_preserved_in_response(response_data):
    evidence = response_data["criteria_results"][0]["evidence"][0]
    evidence.update(type="test_result", title="Sample: registration test", url=None)
    response = EvaluationResponse.model_validate(response_data)
    assert json.loads(response.model_dump_json()) == response_data
    assert response.model_dump()["criteria_results"][0]["evidence"][0]["url"] is None


@pytest.mark.parametrize("url", ["", "  ", 0, 3.5, False, [], {}])
def test_evidence_reference_rejects_invalid_url_values(response_data, url):
    evidence_data = response_data["criteria_results"][0]["evidence"][0]
    evidence_data["url"] = url
    with pytest.raises(ValidationError):
        EvidenceReference.model_validate(evidence_data)


def test_evidence_reference_still_requires_url_field(response_data):
    evidence_data = response_data["criteria_results"][0]["evidence"][0]
    del evidence_data["url"]
    with pytest.raises(ValidationError):
        EvidenceReference.model_validate(evidence_data)


def test_error_response_serialization_matches_contract():
    error_data = {
        "error": {
            "code": "INVALID_REQUEST",
            "message": "Provide a milestone title and at least one acceptance criterion.",
        }
    }
    assert (
        json.loads(ErrorResponse.model_validate(error_data).model_dump_json())
        == error_data
    )


def test_evaluation_response_json_shape(response_data):
    response = EvaluationResponse.model_validate(response_data)
    assert json.loads(response.model_dump_json()) == response_data
    assert list(EvaluationResponse.model_fields) == list(response_data)


@pytest.mark.parametrize("review_required", [False, None, 0, "true"])
def test_human_review_must_be_true(response_data, review_required):
    response_data["human_review_required"] = review_required
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_human_review_field_must_be_present(response_data):
    del response_data["human_review_required"]
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_criterion_order_and_duplicates_are_preserved(request_data, response_data):
    criteria = ["First", "Second", "First"]
    request_data["milestone"]["acceptance_criteria"] = criteria
    for result, criterion in zip(
        response_data["criteria_results"], criteria, strict=True
    ):
        result["criterion"] = criterion

    request = EvaluationRequest.model_validate(request_data)
    response = EvaluationResponse.model_validate(response_data)
    assert request.milestone.acceptance_criteria == criteria
    assert [result.criterion for result in response.criteria_results] == criteria


@pytest.mark.parametrize("field", ["grantor_id", "grantee_id", "funding_agreement_id"])
def test_request_rejects_relationship_fields(request_data, field):
    request_data[field] = "fictional-id"
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


def test_nested_milestone_rejects_relationship_fields(request_data):
    request_data["milestone"]["funding_agreement_id"] = "fictional-id"
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)


def test_response_rejects_relationship_fields(response_data):
    response_data["grantor_id"] = "fictional-id"
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_nested_evidence_rejects_relationship_fields(response_data):
    response_data["criteria_results"][0]["evidence"][0]["grantee_id"] = "fictional-id"
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_models_reject_non_string_and_extra_fields(request_data, response_data):
    request_data["project_name"] = 123
    with pytest.raises(ValidationError):
        EvaluationRequest.model_validate(request_data)

    response_data["criteria_results"][0]["unexpected"] = "undocumented"
    with pytest.raises(ValidationError):
        EvaluationResponse.model_validate(response_data)


def test_direct_milestone_and_criterion_result_validation(request_data, response_data):
    milestone = Milestone.model_validate(request_data["milestone"])
    result = CriterionResult.model_validate(response_data["criteria_results"][0])
    assert milestone.title == "Implement member registration"
    assert result.evidence[0].type == "pull_request"
