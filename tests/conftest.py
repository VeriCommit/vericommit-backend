"""Shared synthetic inputs for mocked AI integration tests; no live AI calls."""

import asyncio
import os

import httpx
import pytest

from vericommit_backend.schemas import EvaluationRequest
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


@pytest.fixture(autouse=True)
def isolate_provider_environment(monkeypatch):
    # Provider tests must not depend on a developer's selected runtime/provider.
    names = [name for name in os.environ if name.startswith("VERICOMMIT_")]
    for name in (
        *names,
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "GROQ_API_KEY",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def block_live_upstreams(monkeypatch):
    # MockTransport bypasses these methods. Loopback permits executable smoke
    # tests against a test-owned server, but never a real GitHub/AI provider.
    original_sync = httpx.HTTPTransport.handle_request
    original_async = httpx.AsyncHTTPTransport.handle_async_request

    def check(request):
        if (
            request.url.host not in {"127.0.0.1", "localhost", "::1"}
            or request.url.port == 11434
        ):
            pytest.fail("Live upstream HTTP is forbidden in tests; use MockTransport.")

    def sync(self, request):
        check(request)
        return original_sync(self, request)

    async def asynchronous(self, request):
        check(request)
        return await original_async(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", asynchronous)


@pytest.fixture
def ai_request():
    dataset = SampleEvidenceProvider().load_dataset()
    return EvaluationRequest(
        project_name="Synthetic registration demonstration",
        repository_url="https://github.com/VeriCommit/vericommit-backend",
        milestone=dataset.milestone,
        evidence_source="sample",
    )


@pytest.fixture
def retrieved_evidence(ai_request):
    return asyncio.run(SampleEvidenceProvider().retrieve(ai_request))


@pytest.fixture
def assessment_payload(retrieved_evidence):
    def make(criterion, status="supported"):
        record = retrieved_evidence.evidence[0]
        return {
            "criterion": criterion,
            "status": status,
            "reasoning": "The excerpt describes form behavior; functioning software is not independently verified.",
            "citations": []
            if status == "insufficient_evidence"
            else [{"evidence_id": record.evidence_id, "quote": record.content[:64]}],
            "uncertainties": []
            if status == "supported"
            else ["Available excerpts do not establish complete scenario coverage."],
            "suggested_next_steps": [
                "Provide a demonstration and complete test results for human review."
            ],
        }

    return make
