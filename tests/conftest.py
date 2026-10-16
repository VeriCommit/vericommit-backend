"""Shared synthetic inputs for mocked AI integration tests; no live AI calls."""

import asyncio

import pytest

from vericommit_backend.schemas import EvaluationRequest
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


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
