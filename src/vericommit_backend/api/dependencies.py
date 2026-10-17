"""Dependency injection points for later business-service implementations."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
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
from vericommit_backend.services.ollama import OllamaCriterionClient
from vericommit_backend.services.sample_evidence import SampleEvidenceProvider


def get_evidence_provider() -> EvidenceProvider:
    return SampleEvidenceProvider()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_ai_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[CriterionAIClient | None]:
    if settings.ai_provider == "ollama":
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url + "/",
            timeout=settings.ollama_timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        ) as http:
            yield OllamaCriterionClient(http, settings.ollama_model)
        return
    key = settings.openai_api_key
    model = settings.ai_model
    options = {}
    if settings.ai_provider == "groq":
        key = settings.groq_api_key
        model = settings.groq_model
        options["base_url"] = "https://api.groq.com/openai/v1"
    if key is None or model is None:
        yield None
        return
    async with AsyncOpenAI(
        api_key=key.get_secret_value(),
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
        # Groq metadata (e.g. service_tier="on_demand") is not an OpenAI enum.
        # The adapter strictly validates the provider-neutral completion fields.
        _strict_response_validation=settings.ai_provider == "openai",
        **options,
    ) as sdk:
        yield OpenAICriterionClient(sdk, model, provider=settings.ai_provider)


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
        timeout_seconds=settings.evaluation_timeout_seconds
        if settings is not None
        else 30,
    )
