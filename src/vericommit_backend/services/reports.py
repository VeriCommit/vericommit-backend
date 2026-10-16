"""Assemble public reports from grounded AI results, not invented conclusions."""

from collections import Counter
from uuid import uuid4

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import (
    CriterionResult,
    EvaluationRequest,
    EvaluationResponse,
)
from vericommit_backend.services.ai import AIEvaluationError


def build_report(
    request: EvaluationRequest,
    evidence: EvidenceCollection,
    results: list[CriterionResult],
    uncertainties: list[str],
    next_steps: list[str],
) -> EvaluationResponse:
    if [
        result.criterion for result in results
    ] != request.milestone.acceptance_criteria:
        raise AIEvaluationError("Report criteria do not match the request.")
    counts = Counter(result.status for result in results)
    return EvaluationResponse(
        evaluation_id=f"eval_{uuid4().hex}",
        project_name=request.project_name,
        milestone_title=request.milestone.title,
        overall_summary=(
            f"AI-assisted assessment of supplied {evidence.source} evidence: "
            f"{counts['supported']} supported, "
            f"{counts['insufficient_evidence']} insufficient_evidence, "
            f"{counts['uncertain']} uncertain. Human review is required; "
            "these findings do not approve a milestone or funding."
        ),
        criteria_results=results,
        suggested_next_steps=[
            *next_steps,
            "A human reviewer must verify evidence and make the final decision.",
        ],
        limitations=[
            *evidence.limitations,
            f"Actual evidence source: {evidence.source}. No source fallback was used.",
            "Quoted excerpts establish only what supplied text says, not that its claims are true. AI interpretations require human verification.",
            "Repository content is untrusted. Activity volume does not establish quality or completion. No funding relationship or ownership is verified.",
            *uncertainties,
        ],
        human_review_required=True,
    )
