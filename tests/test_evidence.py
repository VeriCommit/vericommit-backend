"""Internal evidence validation, normalization and public-reference compatibility."""

import json

import pytest
from pydantic import ValidationError

from vericommit_backend.evidence.models import EvidenceCollection, NormalizedEvidence
from vericommit_backend.evidence.normalization import (
    normalize_github_commit,
    normalize_github_pull_request,
    normalize_github_release,
)
from vericommit_backend.schemas import EvidenceReference


@pytest.fixture
def sample_data():
    return {
        "evidence_id": "sample:demo:form-notes",
        "source_id": "form-notes",
        "source": "sample",
        "type": "pull_request",
        "title": "Sample: registration form notes",
        "content": "Synthetic notes describing a form, not verified project activity.",
    }


@pytest.mark.parametrize(
    "field", ["evidence_id", "source_id", "source", "type", "title"]
)
def test_evidence_requires_identity_type_title_and_provenance(sample_data, field):
    del sample_data[field]
    with pytest.raises(ValidationError):
        NormalizedEvidence.model_validate(sample_data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_id", " "),
        ("source_id", None),
        ("source", "live"),
        ("source", "GitHub"),
        ("type", "sample"),
        ("type", "unknown"),
        ("title", " "),
        ("title", "Unlabelled demonstration"),
        ("title", "Sample: "),
        ("content", 123),
        ("url", "not-a-url"),
        ("url", "https://example.org/a b"),
        ("url", "https://user:secret@example.org/item"),
        ("url", "file:///tmp/example"),
    ],
)
def test_invalid_normalized_evidence(sample_data, field, value):
    sample_data[field] = value
    with pytest.raises(ValidationError):
        NormalizedEvidence.model_validate(sample_data)


@pytest.mark.parametrize("explicit_null", [False, True])
def test_missing_metadata_and_url_are_not_fabricated(sample_data, explicit_null):
    if explicit_null:
        sample_data["url"] = None
    evidence = NormalizedEvidence.model_validate(sample_data)
    assert evidence.url is None
    assert all(value is None for value in evidence.metadata.model_dump().values())
    assert (
        NormalizedEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    )
    reference = evidence.to_public_reference()
    assert type(reference) is EvidenceReference
    assert reference.model_dump() == {
        "type": "pull_request",
        "title": "Sample: registration form notes [sample:demo:form-notes]",
        "url": None,
    }
    assert "url" in json.loads(reference.model_dump_json())
    assert evidence.source_id == "form-notes"
    assert evidence.source == "sample"


def test_source_url_is_preserved_exactly(sample_data):
    # Known source URL used only as a serialization example, never retrieved.
    url = "https://github.com/VeriCommit/vericommit-backend"
    sample_data["url"] = url
    evidence = NormalizedEvidence.model_validate(sample_data)
    assert evidence.to_public_reference().url == url
    assert (
        evidence.source == "sample"
    )  # A URL does not turn sample data into live data.


@pytest.mark.parametrize(
    ("normalize", "payload", "source_id", "kind"),
    [
        (
            normalize_github_commit,
            {"sha": "upstream-sha", "commit": {"message": "Add form\n\nDetails"}},
            "upstream-sha",
            "commit",
        ),
        (
            normalize_github_pull_request,
            {"number": 12, "title": "Add form"},
            "12",
            "pull_request",
        ),
        (
            normalize_github_release,
            {"id": 42, "tag_name": "v0.1.0"},
            "42",
            "release",
        ),
    ],
)
def test_normalization_preserves_stable_scoped_ids_and_missing_metadata(
    normalize, payload, source_id, kind
):
    evidence = normalize("Owner/Repository", payload)
    assert evidence == normalize("Owner/Repository", payload)
    assert evidence.evidence_id == f"github:owner/repository:{kind}:{source_id}"
    assert evidence.evidence_id != normalize("other/repository", payload).evidence_id
    assert evidence.source_id == source_id
    assert evidence.source == "github"
    assert evidence.type == kind
    assert evidence.url is None
    assert evidence.metadata.repository == "Owner/Repository"
    assert evidence.metadata.author is None
    assert (
        NormalizedEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    )
    with pytest.raises(ValueError, match="URL-less public references"):
        evidence.to_public_reference()


def test_raw_github_fields_are_separate_from_normalized_evidence():
    url = "https://github.com/VeriCommit/vericommit-backend/pull/14"
    evidence = normalize_github_pull_request(
        "VeriCommit/vericommit-backend",
        {
            "number": 14,
            "title": "Implement Pydantic evaluation schemas",
            "body": "Supplied body preserved exactly.\n",
            "html_url": url,
            "user": {"login": "upstream-author", "unrelated": "ignored"},
            "raw_provider_field": "not forwarded",
        },
    )
    assert evidence.content == "Supplied body preserved exactly.\n"
    assert evidence.metadata.pull_request_number == 14
    assert evidence.metadata.author == "upstream-author"
    reference = evidence.to_public_reference().model_dump()
    assert set(reference) == {"type", "title", "url"}
    assert reference["url"] == url
    assert evidence.evidence_id in reference["title"]
    assert "raw_provider_field" not in evidence.model_dump()


def test_commit_and_release_content_and_metadata_are_preserved():
    commit = normalize_github_commit(
        "owner/repo",
        {"sha": "sha-from-upstream", "commit": {"message": "Title\nDetails"}},
    )
    assert commit.title == "Title"
    assert commit.content == "Title\nDetails"
    assert commit.metadata.commit_sha == "sha-from-upstream"
    release = normalize_github_release(
        "owner/repo",
        {"id": 42, "tag_name": "v1", "name": "Release one", "body": "Notes"},
    )
    assert release.title == "Release one"
    assert release.content == "Notes"
    assert release.metadata.release_tag == "v1"
    missing = normalize_github_release(
        "owner/repo", {"id": 42, "tag_name": "v1", "name": " ", "body": None}
    )
    assert missing.title == "v1"  # Actual supplied tag, not an invented release name.
    assert missing.content is None


@pytest.mark.parametrize(
    ("normalize", "payload"),
    [
        (normalize_github_commit, {"commit": {"message": "Title"}}),
        (normalize_github_commit, {"sha": "sha", "commit": {"message": " "}}),
        (normalize_github_pull_request, {"number": "12", "title": "Title"}),
        (normalize_github_pull_request, {"number": 12}),
        (normalize_github_release, {"id": 1}),
        (normalize_github_release, {"id": True, "tag_name": "v1"}),
    ],
)
def test_invalid_raw_records_fail_without_inventing_metadata(normalize, payload):
    with pytest.raises(ValidationError):
        normalize("owner/repo", payload)


def test_collections_reject_mixed_provenance_and_duplicate_ids(sample_data):
    sample = NormalizedEvidence.model_validate(sample_data)
    with pytest.raises(ValidationError, match="provenance"):
        EvidenceCollection(source="github", evidence=(sample,))
    with pytest.raises(ValidationError, match="unique"):
        EvidenceCollection(source="sample", evidence=(sample, sample))
    empty = EvidenceCollection(source="github", evidence=())
    assert empty.evidence == ()  # No automatic claim that work was not performed.


def test_internal_evidence_is_immutable_and_has_no_relationship_fields(sample_data):
    evidence = NormalizedEvidence.model_validate(sample_data)
    with pytest.raises(ValidationError, match="frozen"):
        evidence.source = "github"
    sample_data["funding_agreement_id"] = "not-evidence"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        NormalizedEvidence.model_validate(sample_data)
