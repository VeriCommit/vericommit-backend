"""Pure adapters for GitHub-shaped records; these functions make no HTTP requests.

Upstream payload models ignore unrelated GitHub fields. Only explicit normalized
fields reach the evaluator; raw payloads are never mixed into public references.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from vericommit_backend.evidence.models import (
    EvidenceMetadata,
    NormalizedEvidence,
    SourceURL,
)
from vericommit_backend.schemas import NonBlankString

_repository = TypeAdapter(
    Annotated[NonBlankString, Field(pattern=r"^[^/:\s]+/[^/:\s]+$")],
    config=ConfigDict(strict=True),
)


class _GitHubRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class _User(_GitHubRecord):
    login: NonBlankString | None = None


class _CommitBody(_GitHubRecord):
    message: NonBlankString


class _Commit(_GitHubRecord):
    sha: NonBlankString
    commit: _CommitBody
    html_url: SourceURL | None = None
    author: _User | None = None


class _PullRequest(_GitHubRecord):
    number: int = Field(gt=0)
    title: NonBlankString
    body: str | None = None
    html_url: SourceURL | None = None
    user: _User | None = None


class _Release(_GitHubRecord):
    id: int = Field(gt=0)
    tag_name: NonBlankString
    name: str | None = None
    body: str | None = None
    html_url: SourceURL | None = None
    author: _User | None = None


def _optional_text(value: str | None) -> str | None:
    return value if value is not None and value.strip() else None


def normalize_github_commit(repository: str, payload: dict) -> NormalizedEvidence:
    repository = _repository.validate_python(repository)
    record = _Commit.model_validate(payload)
    return NormalizedEvidence(
        evidence_id=f"github:{repository.casefold()}:commit:{record.sha}",
        source="github",
        source_id=record.sha,
        type="commit",
        title=record.commit.message.splitlines()[0],
        url=record.html_url,
        content=record.commit.message,
        metadata=EvidenceMetadata(
            repository=repository,
            commit_sha=record.sha,
            author=record.author.login if record.author else None,
        ),
    )


def normalize_github_pull_request(repository: str, payload: dict) -> NormalizedEvidence:
    repository = _repository.validate_python(repository)
    record = _PullRequest.model_validate(payload)
    return NormalizedEvidence(
        evidence_id=f"github:{repository.casefold()}:pull_request:{record.number}",
        source="github",
        source_id=str(record.number),
        type="pull_request",
        title=record.title,
        url=record.html_url,
        content=_optional_text(record.body),
        metadata=EvidenceMetadata(
            repository=repository,
            pull_request_number=record.number,
            author=record.user.login if record.user else None,
        ),
    )


def normalize_github_release(repository: str, payload: dict) -> NormalizedEvidence:
    repository = _repository.validate_python(repository)
    record = _Release.model_validate(payload)
    return NormalizedEvidence(
        evidence_id=f"github:{repository.casefold()}:release:{record.id}",
        source="github",
        source_id=str(record.id),
        type="release",
        title=_optional_text(record.name) or record.tag_name,
        url=record.html_url,
        content=_optional_text(record.body),
        metadata=EvidenceMetadata(
            repository=repository,
            release_tag=record.tag_name,
            author=record.author.login if record.author else None,
        ),
    )
