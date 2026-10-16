"""Dependency injection points for later business-service implementations."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from openai import AsyncOpenAI

from vericommit_backend.config import Settings
from vericommit_backend.evidence.providers import EvidenceProvider
from vericommit_backend.services.ai import CriterionAIClient, OpenAICriterionClient
from vericommit_backend.services.evaluation import (
    AIEvaluationService,
    EvaluationService,
    UnconfiguredEvaluationService,
)
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def get_evidence_provider() -> EvidenceProvider:
    return SampleEvidenceProvider()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_ai_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[CriterionAIClient | None]:
    if settings.openai_api_key is None:
        yield None
        return
    async with AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
        _strict_response_validation=True,
    ) as sdk:
        yield OpenAICriterionClient(sdk, settings.ai_model)


def get_evaluation_service(
    evidence_provider: Annotated[EvidenceProvider, Depends(get_evidence_provider)],
    ai_client: Annotated[CriterionAIClient | None, Depends(get_ai_client)] = None,
    settings: Annotated[Settings | None, Depends(get_settings)] = None,
) -> EvaluationService:
    if ai_client is None:
        return UnconfiguredEvaluationService(evidence_provider)
    return AIEvaluationService(
        evidence_provider,
        ai_client,
        timeout_seconds=settings.ai_timeout_seconds if settings is not None else 30,
    )
