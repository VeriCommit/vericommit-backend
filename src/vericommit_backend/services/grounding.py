"""Independent citation/quote validation and conservative output policy.

Exact excerpts are verifiable observations of supplied text, not proof that its
claims are true. AI reasoning remains explicitly labelled interpretation.
"""

import re

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import CriterionResult
from vericommit_backend.services.ai import AIEvaluationError, CriterionAssessment


class GroundingError(AIEvaluationError):
    """An assessment failed evidence-grounding or output-policy checks."""


_UNSAFE = re.compile(
    r"https?://|ignore\b.{0,40}\binstructions|(?:reveal|print|expose)\b.{0,40}\b(?:secret|key|token)"
    r"|(?:approve|authorize|release|transfer|reassign)\w*\b.{0,45}\b"
    r"(?:funds?|funding|payment|milestone|agreement|ownership)"
    r"|(?:grantor|grantee|funding.agreement).{0,35}(?:verified|owns?|ownership)"
    r"|(?:eligible|qualif\w*)\b.{0,30}(?:funding|grant)"
    r"|(?:funding|payment|milestone).{0,30}(?:approved|authorized|eligible)"
    r"|(?:work|feature|implementation)\s+(?:was |is )?(?:not done|not implemented|never done)"
    r"|(?:no work|nothing)\s+(?:was |has been )?(?:done|implemented|completed)"
    r"|(?:commit|pull.request|line)\s+count.{0,35}(?:prov|guarante|establish)"
    r"|\d+\s+(?:commits|pull.requests|lines).{0,35}(?:prov|guarante|establish)"
    r"|(?:prov|guarante|establish).{0,35}(?:commit|pull.request|line)\s+count",
    re.IGNORECASE | re.DOTALL,
)


def validate_assessment(
    criterion: str, assessment: CriterionAssessment, evidence: EvidenceCollection
) -> CriterionResult:
    if assessment.criterion != criterion:
        raise GroundingError("AI changed the agreed criterion.")
    records = {item.evidence_id: item for item in evidence.evidence}
    if assessment.status in {"supported", "uncertain"} and not assessment.citations:
        raise GroundingError("This status requires supplied evidence citations.")
    if assessment.status != "supported" and not assessment.uncertainties:
        raise GroundingError("Evidence gaps or uncertainty must be disclosed.")
    prose = [
        assessment.reasoning,
        *assessment.uncertainties,
        *assessment.suggested_next_steps,
    ]
    if any(_UNSAFE.search(text) for text in prose):
        raise GroundingError(
            "AI output violates the evidence or human-decision policy."
        )
    references = []
    excerpts = []
    seen = set()
    for citation in assessment.citations:
        record = records.get(citation.evidence_id)
        if (
            record is None
            or record.content is None
            or citation.quote not in record.content
        ):
            raise GroundingError("AI cited unknown evidence or an invented excerpt.")
        if _UNSAFE.search(citation.quote):
            raise GroundingError(
                "Instructional or unsafe content cannot ground a finding."
            )
        if record.evidence_id in seen:
            raise GroundingError("Duplicate evidence citations are not accepted.")
        seen.add(record.evidence_id)
        references.append(record.to_public_reference())
        excerpts.append(
            f"Supplied untrusted excerpt [{record.evidence_id}]: {citation.quote}"
        )
    prefix = {
        "supported": "Available supplied evidence supports this criterion; this is not verification of working functionality.",
        "insufficient_evidence": "Not demonstrated by available evidence; this does not establish that work was not performed.",
        "uncertain": "Available evidence is ambiguous; human verification is required.",
    }[assessment.status]
    explanation = "\n".join(
        [
            prefix,
            f"AI interpretation (not verified fact): {assessment.reasoning}",
            *excerpts,
        ]
    )
    return CriterionResult(
        criterion=criterion,
        status=assessment.status,
        explanation=explanation,
        evidence=references,
    )
