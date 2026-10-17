"""Bounded public GitHub REST snapshots. Never fetch URLs supplied by API data."""

import asyncio
import json
import re
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vericommit_backend.config import Settings
from vericommit_backend.evidence.models import (
    EvidenceCollection,
    EvidenceMetadata,
    NormalizedEvidence,
    SourceURL,
)
from vericommit_backend.evidence.normalization import (
    normalize_github_commit,
    normalize_github_pull_request,
    normalize_github_release,
)
from vericommit_backend.evidence.providers import (
    EvidenceProviderError,
    EvidenceRateLimitError,
    EvidenceTimeoutError,
    RepositoryAccessDeniedError,
    UnsupportedEvidenceSourceError,
)
from vericommit_backend.schemas import EvaluationRequest, NonBlankString
from vericommit_backend.services.diagnostics import log_failure

MAX_RESPONSE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 4_000_000
MAX_ITEMS = 5  # per evidence kind, independent of configured pagination
MAX_RECORD_CHARS = 3000
MAX_CONTENT_CHARS = 30_000
MAX_FILES = 20
_SHA = re.compile(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})\Z")


def parse_repository(url: str) -> str:
    # Reuse the approved validator, including when called outside FastAPI.
    EvaluationRequest.supported_repository_url(url)
    owner, name = urlsplit(url).path.strip("/").split("/")
    name = name.removesuffix(".git")
    if not name or name in {".", ".."}:
        raise ValueError("Invalid repository name.")
    return f"{owner}/{name}"


class _Record(BaseModel):
    model_config = ConfigDict(strict=True)


class _Repository(_Record):
    full_name: NonBlankString
    private: bool
    visibility: str | None = None
    default_branch: NonBlankString | None = None
    html_url: SourceURL | None = None


class _CommitID(_Record):
    sha: NonBlankString = Field(pattern=r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


class _File(_Record):
    filename: NonBlankString
    status: NonBlankString
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)


class _Run(_Record):
    id: int = Field(gt=0)
    name: NonBlankString
    status: NonBlankString
    conclusion: str | None = None
    head_sha: NonBlankString
    html_url: SourceURL | None = None


class _ScopeLimit(Exception):
    """An intentional local request bound, not an upstream retrieval failure."""


class GitHubEvidenceProvider:
    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.transport = transport  # Internal test injection only; never request data.

    async def retrieve(self, request: EvaluationRequest) -> EvidenceCollection:
        if request.evidence_source != "github":
            raise UnsupportedEvidenceSourceError(
                "GitHub provider requires explicit GitHub mode."
            )
        try:
            repository = parse_repository(request.repository_url)
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "VeriCommit/0.1",
            }
            if self.settings.github_token is not None:
                headers["Authorization"] = (
                    f"Bearer {self.settings.github_token.get_secret_value()}"
                )
            async with asyncio.timeout(self.settings.github_total_timeout_seconds):
                async with httpx.AsyncClient(
                    headers=headers,
                    timeout=self.settings.github_timeout_seconds,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as http:
                    return await _Retrieval(http, self.settings, repository).retrieve()
        except (TimeoutError, httpx.TimeoutException) as exc:
            log_failure("github.retrieve", exc)
            raise EvidenceTimeoutError("GitHub evidence retrieval timed out.") from exc
        except httpx.HTTPError as exc:
            log_failure("github.retrieve", exc)
            raise EvidenceProviderError("GitHub network request failed.") from exc
        except (ValueError, ValidationError, RecursionError) as exc:
            log_failure("github.response", exc)
            raise EvidenceProviderError("GitHub returned invalid evidence.") from exc
        except EvidenceProviderError as exc:
            log_failure("github.retrieve", exc)
            raise


class _Retrieval:
    def __init__(
        self, http: httpx.AsyncClient, settings: Settings, repository: str
    ) -> None:
        self.http, self.settings, self.repository = http, settings, repository
        self.root = f"/repos/{repository}"
        self.requests = self.bytes = 0
        self.records: dict[str, NormalizedEvidence] = {}
        self.notes = [
            "GitHub REST snapshot of a public repository, not a complete history or repository checkout.",
            "Commits use the default branch; pull requests include all states, most recently updated first. Releases, checks and workflow runs are bounded recent records.",
            "Repository descriptions and GitHub-reported changes/check conclusions are untrusted evidence, not independent verification. VeriCommit did not download source files, execute code, or run tests.",
        ]

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    async def get(
        self, path: str, params: dict | None = None, *, empty_repository: bool = False
    ):
        # Callers supply only paths constructed here; redirects and Link URLs are never followed.
        if not path.startswith(self.root + "/") and path != self.root:
            raise EvidenceProviderError(
                "GitHub endpoint is outside the repository scope."
            )
        if self.requests >= self.settings.github_max_requests:
            raise _ScopeLimit
        self.requests += 1
        async with self.http.stream(
            "GET", "https://api.github.com" + path, params=params
        ) as response:
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65_536):
                self.bytes += len(chunk)
                if (
                    len(content) + len(chunk) > MAX_RESPONSE_BYTES
                    or self.bytes > MAX_TOTAL_BYTES
                ):
                    raise EvidenceProviderError(
                        "GitHub response exceeded the data size limit."
                    )
                content.extend(chunk)
            status = response.status_code
            if empty_repository and status == 409:
                data = json.loads(content)
                if (
                    isinstance(data, dict)
                    and data.get("message") == "Git Repository is empty."
                ):
                    self.note(
                        "GitHub reported an empty Git repository; no commit evidence was available."
                    )
                    return []
            if status < 200 or status >= 300:
                log_failure(
                    "github.api",
                    httpx.HTTPStatusError(
                        "GitHub request failed.",
                        request=response.request,
                        response=response,
                    ),
                )
            rate_limited = status == 429 or (
                status == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in response.headers
                )
            )
            if status == 403 and not rate_limited:
                try:
                    error = json.loads(content)
                except (ValueError, RecursionError):
                    error = None
                message = error.get("message") if isinstance(error, dict) else None
                rate_limited = (
                    isinstance(message, str) and "rate limit" in message.casefold()
                )
            if rate_limited:
                raise EvidenceRateLimitError("GitHub rate limit prevented retrieval.")
            if status in {401, 403, 404}:
                raise RepositoryAccessDeniedError(
                    "Repository or required evidence is not accessible."
                )
            if status < 200 or status >= 300:
                raise EvidenceProviderError(
                    "GitHub refused the evidence request; redirects are not followed."
                )
            return json.loads(content)

    async def pages(
        self,
        path: str,
        *,
        params: dict | None = None,
        key: str | None = None,
        limit: int = MAX_ITEMS,
        empty_repository: bool = False,
    ) -> list[dict]:
        result = []
        for page in range(1, self.settings.github_max_pages + 1):
            try:
                data = await self.get(
                    path,
                    {
                        **(params or {}),
                        "per_page": self.settings.github_page_size,
                        "page": page,
                    },
                    empty_repository=empty_repository,
                )
            except _ScopeLimit:
                if not result:
                    raise
                self.note(
                    "Configured request budget reached; remaining GitHub evidence was not fetched."
                )
                return result
            if key is not None:
                if not isinstance(data, dict) or key not in data:
                    raise EvidenceProviderError("Invalid GitHub list envelope.")
                data = data[key]
            if not isinstance(data, list) or not all(
                isinstance(item, dict) for item in data
            ):
                raise EvidenceProviderError("Invalid GitHub evidence list.")
            if len(data) > self.settings.github_page_size:
                raise EvidenceProviderError("GitHub exceeded the requested page size.")
            result.extend(data[: limit - len(result)])
            # Reconstruct numbered pages ourselves; even a malicious Link header
            # can never redirect the token or request to a different endpoint.
            if len(data) < self.settings.github_page_size:
                return result
            if len(result) >= limit:
                break
        self.note(
            "Pagination/item limits reached; additional GitHub records may be omitted."
        )
        return result

    def source_link(self, url: str | None) -> None:
        if url is None:
            return
        parts = urlsplit(url)
        prefix = f"/{self.repository}".casefold()
        if (
            parts.scheme != "https"
            or parts.netloc.casefold() != "github.com"
            or parts.query not in {"", "check_suite_focus=true"}
            or parts.fragment
            or not (
                parts.path.casefold() == prefix
                or parts.path.casefold().startswith(prefix + "/")
            )
        ):
            raise EvidenceProviderError("GitHub supplied an out-of-scope source link.")

    def put(self, record: NormalizedEvidence) -> None:
        self.source_link(record.url)
        self.records[record.evidence_id] = record

    def files_summary(self, files: list) -> str:
        if not isinstance(files, list):
            raise EvidenceProviderError("Invalid GitHub changed-file list.")
        lines = []
        for payload in files[:MAX_FILES]:
            item = _File.model_validate(payload)
            lines.append(
                f"GitHub changed-file metadata: {item.filename}; status={item.status}; additions={item.additions}; deletions={item.deletions}."
            )
        self.note(
            "Changed-file summaries cover only the first page for up to three commits and bounded files for up to two pull requests; patch fields are discarded and full file contents are not downloaded."
        )
        if len(files) > MAX_FILES:
            self.note("Changed-file count limit reached; some filenames were omitted.")
        return "\n".join(lines)

    async def retrieve(self) -> EvidenceCollection:
        metadata = _Repository.model_validate(await self.get(self.root))
        if metadata.private or metadata.visibility not in {None, "public"}:
            raise RepositoryAccessDeniedError("Only public repositories are supported.")
        if metadata.full_name.casefold() != self.repository.casefold():
            raise EvidenceProviderError(
                "GitHub repository identity does not match the request."
            )
        self.source_link(metadata.html_url)
        self.note(
            f"GitHub repository metadata: {metadata.full_name}; default branch: {metadata.default_branch or 'not supplied'}."
        )
        try:
            commits = await self.pages(self.root + "/commits", empty_repository=True)
            for payload in commits:
                _CommitID.model_validate(payload)
                self.put(normalize_github_commit(self.repository, payload))
            pulls = await self.pages(
                self.root + "/pulls",
                params={"state": "all", "sort": "updated", "direction": "desc"},
            )
            for payload in pulls:
                self.put(normalize_github_pull_request(self.repository, payload))
            for payload in await self.pages(self.root + "/releases"):
                self.put(normalize_github_release(self.repository, payload))
            if commits:
                sha = commits[0]["sha"]
                await self.runs(
                    self.root + f"/commits/{sha}/check-runs", "check_runs", "check", sha
                )
                await self.runs(
                    self.root + "/actions/runs", "workflow_runs", "workflow", sha
                )
            for payload in commits[:3]:
                sha = payload["sha"]
                detail = await self.get(
                    self.root + f"/commits/{sha}",
                    {"per_page": self.settings.github_page_size, "page": 1},
                )
                if _CommitID.model_validate(detail).sha != sha:
                    raise EvidenceProviderError(
                        "GitHub commit detail identity mismatch."
                    )
                record = normalize_github_commit(self.repository, detail)
                summary = self.files_summary(detail.get("files", []))
                self.put(
                    record.model_copy(
                        update={
                            "content": record.content
                            + ("\n" + summary if summary else "")
                        }
                    )
                )
            for payload in pulls[:2]:
                record = normalize_github_pull_request(self.repository, payload)
                files = await self.pages(
                    self.root + f"/pulls/{record.metadata.pull_request_number}/files",
                    limit=MAX_FILES,
                )
                summary = self.files_summary(files)
                content = "\n".join(part for part in [record.content, summary] if part)
                self.put(record.model_copy(update={"content": content or None}))
        except _ScopeLimit:
            self.note(
                "Configured request budget reached; remaining GitHub evidence was not fetched."
            )
        remaining = MAX_CONTENT_CHARS
        records = []
        for record in self.records.values():
            content = (
                record.content[: min(MAX_RECORD_CHARS, remaining)]
                if record.content
                else None
            )
            if record.content and content != record.content:
                self.note(
                    "Evidence text was truncated by per-record or total text limits; omitted text was not evaluated."
                )
            remaining -= len(content or "")
            records.append(
                NormalizedEvidence.model_validate(
                    {
                        **record.model_dump(),
                        "title": record.title[:300],
                        "content": content or None,
                    }
                )
            )
        self.note(
            f"Retrieved scope: {len(records)} normalized records in {self.requests} GitHub requests; at most {MAX_ITEMS} records per activity list, {self.settings.github_max_pages} pages per list, and {self.settings.github_page_size} items per page."
        )
        if not records:
            self.note(
                "Successful bounded retrieval supplied no activity evidence; absence does not establish that work was not performed."
            )
        return EvidenceCollection(
            source="github", evidence=tuple(records), limitations=tuple(self.notes)
        )

    async def runs(self, path: str, key: str, kind: str, sha: str) -> None:
        params = {"head_sha": sha} if kind == "workflow" else {"filter": "latest"}
        for payload in await self.pages(path, params=params, key=key):
            run = _Run.model_validate(payload)
            if run.head_sha != sha or not _SHA.fullmatch(run.head_sha):
                raise EvidenceProviderError(
                    "GitHub check/workflow commit identity mismatch."
                )
            self.put(
                NormalizedEvidence(
                    evidence_id=f"github:{self.repository.casefold()}:test_result:{kind}-{run.id}",
                    source="github",
                    source_id=f"{kind}-{run.id}",
                    type="test_result",
                    title=f"GitHub {kind}: {run.name}",
                    url=run.html_url,
                    content=f"GitHub {kind} reported name: {run.name}; status: {run.status}; conclusion: {run.conclusion or 'not supplied'}.",
                    metadata=EvidenceMetadata(
                        repository=self.repository, commit_sha=sha
                    ),
                )
            )
