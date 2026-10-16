"""Dependency injection points for later business-service implementations."""

from typing import Annotated

from fastapi import Depends

from vericommit_backend.evidence.providers import EvidenceProvider
from vericommit_backend.services.evaluation import (
    EvaluationService,
    UnconfiguredEvaluationService,
)
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def get_evidence_provider() -> EvidenceProvider:
    return SampleEvidenceProvider()


def get_evaluation_service(
    evidence_provider: Annotated[EvidenceProvider, Depends(get_evidence_provider)],
) -> EvaluationService:
    return UnconfiguredEvaluationService(evidence_provider)
