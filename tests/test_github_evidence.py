"""Bounded native GitHub REST retrieval and the actual pipeline with mocked HTTP."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vericommit_backend.api import dependencies
from vericommit_backend.api.dependencies import get_ai_client
from vericommit_backend.config import Settings
from vericommit_backend.evidence.providers import (
    EvidenceProviderError,
    EvidenceSourceRouter,
    EvidenceTimeoutError,
)
from vericommit_backend.main import create_app
from vericommit_backend.schemas import EvaluationResponse
from vericommit_backend.services.ai import CriterionAIClient
from vericommit_backend.services.github_evidence import (
    GitHubEvidenceProvider,
    parse_repository,
)

SHA = "a" * 40
REPO = "VeriCommit/vericommit-backend"
ROOT = f"/repos/{REPO}"
LINK = f"https://github.com/{REPO}"


@pytest.fixture
def github_request(ai_request):
    return ai_request.model_copy(update={"evidence_source": "github"})


def commit(sha=SHA):
    return {
        "sha": sha,
        "commit": {
            "message": "Add registration form\nValidate email before storing account data."
        },
        "html_url": f"{LINK}/commit/{sha}",
    }


def pull(number=7):
    return {
        "number": number,
        "title": "Add registration validation",
        "body": "Registration rejects invalid email and missing names.",
        "html_url": f"{LINK}/pull/{number}",
    }


def file():
    return {
        "filename": "src/registration.py",
        "status": "modified",
        "additions": 12,
        "deletions": 2,
        "patch": "private-patch-not-forwarded",
        "raw_url": "http://127.0.0.1/private",
    }


def routes():
    return {
        ROOT: {
            "full_name": REPO,
            "private": False,
            "default_branch": "staging",
            "html_url": LINK,
        },
        ROOT + "/commits": [commit()],
        ROOT + "/commits/" + SHA: {**commit(), "files": [file()]},
        ROOT + "/pulls": [pull()],
        ROOT + "/pulls/7/files": [file()],
        ROOT + "/releases": [
            {
                "id": 12,
                "tag_name": "v0.1",
                "name": "Initial release",
                "body": "Registration demonstration release notes.",
                "html_url": LINK + "/releases/tag/v0.1",
            }
        ],
        ROOT + f"/commits/{SHA}/check-runs": {
            "check_runs": [
                {
                    "id": 8,
                    "name": "Registration tests",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": SHA,
                    "html_url": LINK + "/runs/8",
                }
            ]
        },
        ROOT + "/actions/runs": {
            "workflow_runs": [
                {
                    "id": 9,
                    "name": "CI",
                    "status": "completed",
                    "conclusion": "success",
                    "head_sha": SHA,
                    "html_url": LINK + "/actions/runs/9",
                }
            ]
        },
    }


def provider(handler, **settings):
    return GitHubEvidenceProvider(
        Settings(_env_file=None, **settings), transport=httpx.MockTransport(handler)
    )


def test_public_retrieval_normalizes_real_links_and_changed_file_metadata(
    github_request, caplog
):
    data, calls = routes(), []

    def handler(request):
        calls.append(request)
        assert request.url.scheme == "https" and request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        assert request.headers["x-github-api-version"] == "2022-11-28"
        return httpx.Response(200, json=data[request.url.path])

    with caplog.at_level("DEBUG"):
        collection = asyncio.run(provider(handler).retrieve(github_request))
    assert len(calls) == 8
    assert collection.source == "github"
    assert [record.type for record in collection.evidence] == [
        "commit",
        "pull_request",
        "release",
        "test_result",
        "test_result",
    ]
    for record in collection.evidence:
        assert record.evidence_id.startswith(f"github:{REPO.casefold()}:")
        assert record.metadata.repository == REPO
        assert record.url.startswith(LINK + "/")
        assert record.to_public_reference().url == record.url
    assert "src/registration.py" in collection.evidence[0].content
    assert "private-patch" not in collection.model_dump_json()
    assert "raw_url" not in collection.model_dump_json()
    assert "conclusion: success" in collection.evidence[3].content
    assert "not independent verification" in " ".join(collection.limitations)
    assert "private" not in caplog.text
    assert collection.evidence[1].content not in caplog.text


@pytest.mark.parametrize(
    "url,expected",
    [
        (LINK, REPO),
        (LINK + "/", REPO),
        (LINK + ".git", REPO),
        ("https://GITHUB.COM/Owner/repo.name", "Owner/repo.name"),
    ],
)
def test_approved_urls_are_parsed_without_changing_request(url, expected):
    assert parse_repository(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://github.com.evil.test/a/b",
        "https://user:private@github.com/a/b",
        "https://github.com/a/b?private=1",
        "https://github.com/a/../b",
        "https://github.com/a/%2e%2e",
        "https://127.0.0.1/a/b",
        "https://github.com:443/a/b",
        "https://github.com/a/.git",
    ],
)
def test_unsafe_repository_urls_never_make_requests(url, github_request):
    def forbidden(request):
        pytest.fail("Invalid URL made an HTTP request")

    with pytest.raises(EvidenceProviderError) as exc_info:
        asyncio.run(
            provider(forbidden).retrieve(
                github_request.model_copy(update={"repository_url": url})
            )
        )
    assert "private" not in str(exc_info.value)


def test_token_is_server_only_and_only_fixed_endpoints_are_requested(
    github_request, caplog
):
    data = routes()
    calls = []

    def handler(request):
        calls.append(request.url)
        assert request.url.host == "api.github.com"
        assert request.headers["authorization"] == "Bearer private-github-token"
        return httpx.Response(
            200,
            json=data[request.url.path],
            headers={"Link": '<http://127.0.0.1/private>; rel="next"'},
        )

    settings = Settings(_env_file=None, VERICOMMIT_GITHUB_TOKEN="private-github-token")
    assert "github_token" not in settings.model_dump()
    assert "private-github-token" not in repr(settings)
    with caplog.at_level("DEBUG"):
        collection = asyncio.run(
            provider(handler, VERICOMMIT_GITHUB_TOKEN="private-github-token").retrieve(
                github_request
            )
        )
    assert len(calls) == 8
    assert "private-github-token" not in caplog.text + collection.model_dump_json()
    assert "Authorization" not in caplog.text


def test_pagination_is_reconstructed_bounded_and_disclosed(github_request):
    calls, data = [], routes()

    def handler(request):
        calls.append(request.url)
        if request.url.path in {ROOT + "/commits", ROOT + "/pulls", ROOT + "/releases"}:
            if request.url.path.endswith("/pulls"):
                number = int(request.url.params["page"])
                return httpx.Response(
                    200,
                    json=[pull(number)],
                    headers={"Link": '<https://evil.test/token>; rel="next"'},
                )
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=data[request.url.path])

    collection = asyncio.run(
        provider(handler, github_page_size=1, github_max_pages=2).retrieve(
            github_request
        )
    )
    pages = [url.params["page"] for url in calls if url.path == ROOT + "/pulls"]
    assert pages == ["1", "2"]
    assert all(url.host == "api.github.com" for url in calls)
    assert len(collection.evidence) == 2
    assert any("Pagination" in note for note in collection.limitations)


@pytest.mark.parametrize("empty_commit_status", [200, 409])
def test_empty_repository_is_successful_but_evidence_poor(
    github_request, empty_commit_status
):
    def handler(request):
        if request.url.path == ROOT:
            return httpx.Response(200, json=routes()[ROOT])
        if request.url.path.endswith("/commits") and empty_commit_status == 409:
            return httpx.Response(409, json={"message": "Git Repository is empty."})
        return httpx.Response(200, json=[])

    collection = asyncio.run(provider(handler).retrieve(github_request))
    assert collection.evidence == ()
    assert any("no activity evidence" in note for note in collection.limitations)


def test_intentional_request_bound_is_disclosed_not_a_hidden_network_failure(
    github_request,
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=routes()[ROOT])

    collection = asyncio.run(
        provider(handler, github_max_requests=1).retrieve(github_request)
    )
    assert len(calls) == 1
    assert collection.evidence == ()
    assert any("request budget" in note for note in collection.limitations)


@pytest.mark.parametrize(
    "defect",
    [
        "malformed",
        "private",
        "identity",
        "unsafe_link",
        "unsafe_sha",
        "wrong_sha",
        "wrong_check_sha",
        "invalid_number",
        "oversized",
        "late_failure",
        "redirect",
        "timeout",
        "network",
        401,
        403,
        404,
        429,
        500,
        "rate_403",
        "secondary_rate",
        "rate_body",
        "internal",
    ],
)
def test_failures_use_approved_errors_and_stop_before_ai(
    defect, github_request, monkeypatch, caplog
):
    data, calls = routes(), []
    if defect == "private":
        data[ROOT]["private"] = True
    elif defect == "internal":
        data[ROOT]["visibility"] = "internal"
    elif defect == "identity":
        data[ROOT]["full_name"] = "other/repo"
    elif defect == "unsafe_link":
        data[ROOT + "/commits"][0]["html_url"] = "http://127.0.0.1/private"
    elif defect == "unsafe_sha":
        data[ROOT + "/commits"][0]["sha"] = "../../private"
    elif defect == "wrong_sha":
        data[ROOT + "/commits/" + SHA]["sha"] = "b" * 40
    elif defect == "wrong_check_sha":
        data[ROOT + f"/commits/{SHA}/check-runs"]["check_runs"][0]["head_sha"] = (
            "b" * 40
        )
    elif defect == "invalid_number":
        data[ROOT + "/pulls"][0]["number"] = "7/private"

    def handler(request):
        calls.append(request)
        if defect == "timeout":
            raise httpx.ReadTimeout("private timeout", request=request)
        if defect == "network":
            raise httpx.ConnectError("private network", request=request)
        if isinstance(defect, int):
            return httpx.Response(defect, json={"message": "private upstream body"})
        if defect in {"rate_403", "secondary_rate"}:
            headers = (
                {"x-ratelimit-remaining": "0"}
                if defect == "rate_403"
                else {"retry-after": "60"}
            )
            return httpx.Response(
                403, headers=headers, json={"message": "private rate body"}
            )
        if defect == "rate_body":
            return httpx.Response(
                403, json={"message": "private: secondary rate limit exceeded"}
            )
        if defect == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        if defect == "malformed":
            return httpx.Response(200, content=b"private invalid json")
        if defect == "oversized":
            return httpx.Response(200, content=b"x" * 1_000_001)
        if defect == "late_failure" and request.url.path.endswith("/releases"):
            return httpx.Response(500, json={"message": "private late failure"})
        return httpx.Response(200, json=data[request.url.path])

    live = provider(handler, VERICOMMIT_GITHUB_TOKEN="private-token")
    monkeypatch.setattr(dependencies, "GitHubEvidenceProvider", lambda settings: live)
    ai = AsyncMock(spec=CriterionAIClient)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_ai_client] = lambda: ai
    with caplog.at_level("DEBUG"), TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=github_request.model_dump(mode="json")
        )
    denied = defect in {401, 403, 404, "private", "internal"}
    assert response.status_code == (
        403 if denied else 504 if defect == "timeout" else 502
    )
    assert response.json()["error"]["code"] == (
        "REPOSITORY_ACCESS_DENIED" if denied else "EVIDENCE_RETRIEVAL_FAILED"
    )
    assert "private" not in response.text + caplog.text
    assert all(request.url.host == "api.github.com" for request in calls)
    ai.assess.assert_not_awaited()


@pytest.mark.parametrize("invented", [False, True])
def test_github_to_ai_endpoint_with_real_adapters_and_mocked_upstreams(
    github_request, monkeypatch, invented
):
    from openai import AsyncOpenAI

    data = routes()
    live = provider(lambda request: httpx.Response(200, json=data[request.url.path]))
    monkeypatch.setattr(dependencies, "GitHubEvidenceProvider", lambda settings: live)
    seen = []

    def ai_handler(request):
        body = json.loads(request.content)
        payload = json.loads(body["messages"][1]["content"])
        assert payload["source"] == "github"
        record = payload["evidence"][0]
        assert record["source"] == "github"
        assert all(
            item["evidence_id"].startswith("github:") for item in payload["evidence"]
        )
        seen.append(payload["criterion"])
        output = {
            "criterion": payload["criterion"],
            "status": "supported",
            "reasoning": "The supplied excerpt describes registration validation; execution is not independently verified.",
            "citations": [
                {
                    "evidence_id": "github:invented:commit:fake"
                    if invented
                    else record["evidence_id"],
                    "quote": record["content"].splitlines()[0],
                }
            ],
            "uncertainties": [],
            "suggested_next_steps": ["Review the implementation and test results."],
        }
        return httpx.Response(
            200,
            json={
                "id": "mock-ai",
                "object": "chat.completion",
                "created": 0,
                "model": "configured-model",
                "service_tier": "on_demand",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(output)},
                    }
                ],
            },
        )

    monkeypatch.setattr(
        dependencies,
        "AsyncOpenAI",
        lambda **kwargs: AsyncOpenAI(
            **kwargs,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(ai_handler)),
        ),
    )
    app = create_app(
        Settings(
            _env_file=None,
            ai_provider="groq",
            VERICOMMIT_GROQ_API_KEY="test-only",
            groq_model="configured-model",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/evaluations", json=github_request.model_dump(mode="json")
        )
    if invented:
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "EVALUATION_FAILED"
    else:
        assert response.status_code == 200
        report = EvaluationResponse.model_validate(response.json())
        assert report.human_review_required is True
        assert [
            result.criterion for result in report.criteria_results
        ] == github_request.milestone.acceptance_criteria
        assert seen == github_request.milestone.acceptance_criteria
        assert all(
            ref.url.startswith(LINK)
            for result in report.criteria_results
            for ref in result.evidence
        )
        assert any(
            "Actual evidence source: github" in note for note in report.limitations
        )


def test_sample_routing_never_touches_github(ai_request):
    sample, github = AsyncMock(), AsyncMock()
    asyncio.run(EvidenceSourceRouter(sample, github).retrieve(ai_request))
    sample.retrieve.assert_awaited_once_with(ai_request)
    github.retrieve.assert_not_awaited()


def test_github_secret_and_resource_configuration(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "private-env-token")
    settings = Settings(_env_file=None)
    assert settings.github_token.get_secret_value() == "private-env-token"
    assert "github_token" not in settings.model_dump()
    assert "private-env-token" not in repr(settings)
    for invalid in (
        {"github_max_pages": 4},
        {"github_max_requests": 101},
        {"github_timeout_seconds": 0},
        {"github_total_timeout_seconds": 121},
        {"github_page_size": 21},
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **invalid)


def test_whole_retrieval_deadline_is_enforced(github_request):
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=routes()[ROOT])

    with pytest.raises(EvidenceTimeoutError):
        asyncio.run(
            provider(slow, github_total_timeout_seconds=0.01).retrieve(github_request)
        )


def test_request_budget_preserves_successfully_retrieved_pages(github_request):
    data = routes()
    collection = asyncio.run(
        provider(
            lambda request: httpx.Response(200, json=data[request.url.path]),
            github_page_size=1,
            github_max_pages=2,
            github_max_requests=2,
        ).retrieve(github_request)
    )
    assert len(collection.evidence) == 1
    assert collection.evidence[0].source_id == SHA
    assert any("request budget" in note for note in collection.limitations)


def test_genuine_check_focus_link_is_preserved_not_fetched(github_request):
    data = routes()
    link = LINK + "/runs/8?check_suite_focus=true"
    data[ROOT + f"/commits/{SHA}/check-runs"]["check_runs"][0]["html_url"] = link
    collection = asyncio.run(
        provider(
            lambda request: httpx.Response(200, json=data[request.url.path])
        ).retrieve(github_request)
    )
    assert any(record.url == link for record in collection.evidence)


def test_aggregate_response_budget_is_enforced(github_request, monkeypatch):
    from vericommit_backend.services import github_evidence

    data = routes()
    monkeypatch.setattr(
        github_evidence, "MAX_TOTAL_BYTES", len(json.dumps(data[ROOT]).encode()) + 50
    )
    with pytest.raises(EvidenceProviderError, match="data size limit"):
        asyncio.run(
            provider(
                lambda request: httpx.Response(200, json=data[request.url.path])
            ).retrieve(github_request)
        )


def test_partial_available_evidence_and_text_truncation_are_disclosed(github_request):
    data = routes()
    data[ROOT + "/pulls"] = []
    data[ROOT + "/releases"] = []
    data[ROOT + f"/commits/{SHA}/check-runs"] = {"check_runs": []}
    data[ROOT + "/actions/runs"] = {"workflow_runs": []}
    data[ROOT + "/commits/" + SHA]["commit"] = {
        "message": "Actual commit description\n" + "x" * 5000
    }
    collection = asyncio.run(
        provider(
            lambda request: httpx.Response(200, json=data[request.url.path])
        ).retrieve(github_request)
    )
    assert len(collection.evidence) == 1
    assert len(collection.evidence[0].content) == 3000
    assert collection.evidence[0].url == LINK + "/commit/" + SHA
    assert any("truncated" in note for note in collection.limitations)
