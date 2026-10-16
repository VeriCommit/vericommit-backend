"""Independent citation/quote validation and conservative output policy.

Exact excerpts are verifiable observations of supplied text, not proof that its
claims are true. AI reasoning remains explicitly labelled interpretation.
"""

import re

from vericommit_backend.evidence.models import EvidenceCollection
from vericommit_backend.schemas import CriterionResult
from vericommit_backend.services.ai import AIEvaluationError, CriterionAssessment
from vericommit_backend.services.evidence_safety import (
    contains_evaluator_instructions,
    is_activity_only,
)


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

_RELATIONSHIP_CLAIM = re.compile(
    r"\b(?:grantor|grantee)\b.{0,50}\b(?:funds?|finances?|owns?|verified|responsible)\b"
    r"|\b(?:milestone|agreement)\b.{0,50}\b(?:belongs?|assigned|reassigned|owned)\b"
    r"|\b(?:verified|confirmed|established)\b.{0,35}\bfunding.relationship\b"
    r"|\bfunding.relationship\b.{0,35}\b(?:verified|confirmed|established)\b",
    re.IGNORECASE | re.DOTALL,
)

_VERIFICATION_CLAIM = re.compile(
    r"\b(?:I|we|the evaluator)\s+(?:independently\s+)?(?:verified|confirmed|executed|ran)\b"
    r"|\b(?:functionality|implementation|feature)\s+(?:is|was|has been)\s+"
    r"(?:independently\s+)?(?:verified|proven|production.ready)\b",
    re.IGNORECASE,
)
_SOURCE_LOCATOR = re.compile(
    r"\b(?:sample|github):[^\s\]\[(),;]+"
    r"|\b[0-9a-fA-F]{7,40}\b|(?<!\w)#\d+\b"
    r"|\b[\w.-]+(?:/[\w.-]+)*\.(?:py|tsx?|jsx?|json|ya?ml|sql|go|rs)\b"
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
    if any(
        _UNSAFE.search(text)
        or _RELATIONSHIP_CLAIM.search(text)
        or _VERIFICATION_CLAIM.search(text)
        or contains_evaluator_instructions(text)
        for text in prose
    ):
        raise GroundingError(
            "AI output violates the evidence or human-decision policy."
        )
    references = []
    excerpts = []
    seen = set()
    substantive_citation = False
    cited_records = []
    for citation in assessment.citations:
        record = records.get(citation.evidence_id)
        if (
            record is None
            or record.content is None
            or len(citation.quote.strip()) < 12
            or citation.quote not in record.content
        ):
            raise GroundingError("AI cited unknown evidence or an invented excerpt.")
        if (
            _UNSAFE.search(citation.quote)
            or _RELATIONSHIP_CLAIM.search(citation.quote)
            or contains_evaluator_instructions(record.title)
            or contains_evaluator_instructions(record.content)
        ):
            raise GroundingError(
                "Instructional or unsafe content cannot ground a finding."
            )
        if record.evidence_id in seen:
            raise GroundingError("Duplicate evidence citations are not accepted.")
        seen.add(record.evidence_id)
        cited_records.append(record)
        substantive_citation |= not is_activity_only(citation.quote)
        references.append(record.to_public_reference())
        excerpts.append(
            f"Supplied untrusted excerpt [{record.evidence_id}]: {citation.quote}"
        )
    if assessment.status == "supported" and not substantive_citation:
        raise GroundingError(
            "Activity volume alone cannot establish criterion support."
        )
    # Source identifiers in prose must also be present in cited records. A valid
    # citation must not be used to launder a different invented commit/file/ID.
    authorized_text = "\n".join(record.model_dump_json() for record in cited_records)
    authorized_prs = {
        f"#{record.metadata.pull_request_number}"
        for record in cited_records
        if record.metadata.pull_request_number is not None
    }
    if any(
        locator.rstrip(".") not in authorized_text and locator not in authorized_prs
        for text in prose
        for locator in _SOURCE_LOCATOR.findall(text)
    ):
        raise GroundingError(
            "AI prose contains an uncited or invented source reference."
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
            *[
                f"AI-reported gap/uncertainty (not verified fact): {gap}"
                for gap in assessment.uncertainties
            ],
        ]
    )
    return CriterionResult(
        criterion=criterion,
        status=assessment.status,
        explanation=explanation,
        evidence=references,
    )
