"""Deterministic offline evidence and compatibility with the evaluation boundary."""

import asyncio
import json
import socket
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vericommit_backend.api.dependencies import (
    get_evaluation_service,
    get_evidence_provider,
)
from vericommit_backend.config import Settings
from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.evidence.providers import (
    EvidenceProvider,
    UnsupportedEvidenceSourceError,
)
from vericommit_backend.main import create_app
from vericommit_backend.schemas import EvaluationRequest
from vericommit_backend.services.sample_evidence import (
    SAMPLE_FIXTURE_ID,
    SampleEvidenceError,
    SampleEvidenceProvider,
)


@pytest.fixture
def sample_request():
    dataset = SampleEvidenceProvider().load_dataset()
    return EvaluationRequest(
        project_name="Illustrative registration demo",
        repository_url="https://github.com/VeriCommit/vericommit-backend",
        milestone=dataset.milestone,
        evidence_source="sample",
    )


@pytest.fixture
def fixture_data():
    return SampleEvidenceProvider().load_dataset().model_dump(mode="json")


def test_sample_selection_is_repeatable_and_independent_of_request_context(
    sample_request, monkeypatch, tmp_path
):
    original_request = sample_request.model_dump(mode="json")
    first = asyncio.run(SampleEvidenceProvider().retrieve(sample_request))
    monkeypatch.chdir(tmp_path)
    second = asyncio.run(SampleEvidenceProvider().retrieve(sample_request))
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first is not second
    assert first.evidence[0] is not second.evidence[0]
    assert sample_request.model_dump(mode="json") == original_request

    different = sample_request.model_copy(deep=True)
    different.project_name = "Different project"
    different.milestone.acceptance_criteria = ["A different agreed criterion"]
    assert asyncio.run(SampleEvidenceProvider().retrieve(different)) == first
    assert EvidenceCollection.model_validate_json(first.model_dump_json()) == first


def test_fixture_labels_ids_references_and_evidence_gaps(sample_request):
    provider = SampleEvidenceProvider()
    dataset = provider.load_dataset()
    result = asyncio.run(provider.retrieve(sample_request))
    assert dataset.fixture_id == SAMPLE_FIXTURE_ID
    assert result.source == "sample"
    assert len(dataset.milestone.acceptance_criteria) == 3
    assert {item.type for item in result.evidence} == {
        "commit",
        "pull_request",
        "release",
        "test_result",
    }
    ids = [item.evidence_id for item in result.evidence]
    assert len(ids) == len(set(ids)) == 4
    assert all(
        item.evidence_id == f"sample:{SAMPLE_FIXTURE_ID}:{item.source_id}"
        for item in result.evidence
    )
    for item in result.evidence:
        assert item.source == "sample"
        assert item.title.startswith("Sample: ")
        assert "synthetic" in item.content.lower()
        assert item.url is None
        assert all(value is None for value in item.metadata.model_dump().values())
        public = json.loads(item.to_public_reference().model_dump_json())
        assert set(public) == {"type", "title", "url"}
        assert public["url"] is None
        assert public["title"].startswith("Sample: ")
        assert item.evidence_id in public["title"]
        assert "github.com" not in json.dumps(public)
    notes = " ".join(result.limitations).lower()
    assert "no live github retrieval" in notes
    assert "invalid-input" in notes
    assert "does not establish" in notes
    assert "missing evidence does not establish that work was not performed" in notes


def test_sample_retrieval_has_no_live_network_dependency(sample_request, monkeypatch):
    def reject_network(*args, **kwargs):
        pytest.fail("Sample mode attempted a network connection")

    async def retrieve_without_network():
        # Patch after loop creation so Windows can set up its own event-loop sockets.
        with monkeypatch.context() as patch:
            patch.setattr(socket.socket, "connect", reject_network)
            patch.setattr(socket.socket, "connect_ex", reject_network)
            patch.setattr(socket, "create_connection", reject_network)
            return await SampleEvidenceProvider().retrieve(sample_request)

    assert asyncio.run(retrieve_without_network()).source == "sample"


def test_provider_rejects_github_before_loading_any_fixture(sample_request, tmp_path):
    request = sample_request.model_copy(update={"evidence_source": "github"})
    provider = SampleEvidenceProvider(tmp_path / "missing.json")
    with pytest.raises(UnsupportedEvidenceSourceError, match="explicit sample mode"):
        asyncio.run(provider.retrieve(request))


def test_missing_fixture_is_an_explicit_failure(sample_request, tmp_path):
    provider = SampleEvidenceProvider(tmp_path / "missing.json")
    with pytest.raises(SampleEvidenceError, match="could not be read"):
        asyncio.run(provider.retrieve(sample_request))


@pytest.mark.parametrize("contents", [b"{", b"[]", b"null", b"\xff"])
def test_malformed_fixture_is_an_explicit_failure(sample_request, tmp_path, contents):
    path = tmp_path / "malformed.json"
    path.write_bytes(contents)
    with pytest.raises(SampleEvidenceError):
        asyncio.run(SampleEvidenceProvider(path).retrieve(sample_request))


@pytest.mark.parametrize(
    "defect",
    [
        "source",
        "item_source",
        "label",
        "id",
        "duplicates",
        "empty",
        "url",
        "missing_source",
    ],
)
def test_invalid_fixtures_are_not_returned_as_empty_success(
    sample_request, fixture_data, tmp_path, defect
):
    if defect == "source":
        fixture_data["source"] = "github"
    elif defect == "item_source":
        fixture_data["evidence"][0]["source"] = "github"
    elif defect == "label":
        fixture_data["evidence"][0]["title"] = "Unlabelled record"
    elif defect == "id":
        fixture_data["evidence"][0]["evidence_id"] = "unscoped-id"
    elif defect == "duplicates":
        fixture_data["evidence"].append(fixture_data["evidence"][0])
    elif defect == "empty":
        fixture_data["evidence"] = []
    elif defect == "url":
        fixture_data["evidence"][0]["url"] = "not-a-url"
    else:
        del fixture_data["evidence"][0]["source"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(fixture_data), encoding="utf-8")
    with pytest.raises(SampleEvidenceError, match="fixture is invalid"):
        asyncio.run(SampleEvidenceProvider(path).retrieve(sample_request))


def test_unsupported_fixture_id_fails_explicitly(
    sample_request, fixture_data, tmp_path
):
    fixture_data["fixture_id"] = "unsupported-demo"
    for item in fixture_data["evidence"]:
        item["evidence_id"] = f"sample:unsupported-demo:{item['source_id']}"
    path = tmp_path / "unsupported.json"
    path.write_text(json.dumps(fixture_data), encoding="utf-8")
    with pytest.raises(
        SampleEvidenceError, match="Unsupported sample evidence fixture"
    ):
        asyncio.run(SampleEvidenceProvider(path).retrieve(sample_request))


def test_supplied_genuine_url_is_preserved_without_changing_sample_provenance(
    sample_request, fixture_data, tmp_path
):
    # An actual repository URL as an illustrative source, never a fake commit/PR link.
    url = "https://github.com/VeriCommit/vericommit-backend"
    fixture_data["evidence"][0]["url"] = url
    path = tmp_path / "with-url.json"
    path.write_text(json.dumps(fixture_data), encoding="utf-8")
    result = asyncio.run(SampleEvidenceProvider(path).retrieve(sample_request))
    item = result.evidence[0]
    assert item.source == "sample"
    assert item.to_public_reference().url == url
    assert item.to_public_reference().title.startswith("Sample: ")


def test_returned_evidence_cannot_be_relabelled_as_live(sample_request):
    result = asyncio.run(SampleEvidenceProvider().retrieve(sample_request))
    with pytest.raises(ValidationError, match="frozen"):
        result.evidence[0].source = "github"


def test_fastapi_boundary_injects_provider_but_does_not_invent_evaluations(
    sample_request,
):
    application = create_app(Settings(_env_file=None))
    provider = SampleEvidenceProvider()
    captured = []

    def capture_service(
        evidence_provider: Annotated[EvidenceProvider, Depends(get_evidence_provider)],
    ):
        service = get_evaluation_service(evidence_provider)
        captured.append(service)
        return service

    application.dependency_overrides[get_evidence_provider] = lambda: provider
    application.dependency_overrides[get_evaluation_service] = capture_service
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/evaluations", json=sample_request.model_dump(mode="json")
        )
        assert client.get("/health").status_code == 200
        assert set(client.get("/openapi.json").json()["paths"]) == {
            "/health",
            "/api/v1/evaluations",
        }
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EVALUATION_FAILED"
    assert captured[0].evidence_provider is provider
    evidence = asyncio.run(captured[0].evidence_provider.retrieve(sample_request))
    assert evidence.source == "sample"
    assert evidence.evidence


def test_default_evaluator_does_not_retrieve_evidence_prematurely(sample_request):
    application = create_app(Settings(_env_file=None))
    provider = AsyncMock(spec=EvidenceProvider)
    application.dependency_overrides[get_evidence_provider] = lambda: provider
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/evaluations", json=sample_request.model_dump(mode="json")
        )
    assert response.status_code == 502
    provider.retrieve.assert_not_awaited()
