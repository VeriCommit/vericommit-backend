"""Targeted evidence-text checks, separate from AI assessment and provenance.

These checks reject known evaluator instructions and activity-only excerpts. They
are deliberately conservative, not a semantic truth or universal injection detector.
"""

import re

_INSTRUCTIONS = re.compile(
    r"\b(?:ignore|disregard|override)\b.{0,60}\b(?:instructions?|rules?|system|prompts?)\b"
    r"|\b(?:reveal|print|expose)\b.{0,40}\b(?:secrets?|keys?|tokens?)\b"
    r"|\b(?:mark|set|return|report)\b.{0,30}\b(?:all|every)\b.{0,35}\bsupported\b"
    r"|<\s*/?\s*(?:system|developer)\b|\[im_start\]\s*(?:system|developer)"
    r"|(?:^|\n)\s*(?:#{1,6}\s*)?(?:system|developer)\s*:"
    r"|\b(?:you are now|act as)\s+(?:the\s+)?(?:system|developer|administrator)\b"
    r"|\b(?:skip|bypass|disable|waive)\w*\b.{0,30}\b(?:human|manual)\s+review\b"
    r"|\b(?:human|manual)\s+review\s+(?:is\s+)?(?:not required|optional|unnecessary)\b"
    r"|\bno\s+(?:human|manual)\s+review\s+(?:is\s+)?(?:required|needed)\b"
    r"|\b(?:approve|authorize|release|transfer|reassign)\w*\b.{0,45}\b"
    r"(?:funds?|funding|payments?|milestones?|agreements?|ownership)\b",
    re.IGNORECASE | re.DOTALL,
)

_ACTIVITY_METRIC = re.compile(
    r"\b\d+\s+(?:commits?|pull[ -]requests?|merges?|lines(?:\s+(?:changed|of code))?)\b"
    r"|\b(?:commit|pull[ -]request|line)\s+count\s*[:=]?\s*\d+\b",
    re.IGNORECASE,
)
_ACTIVITY_BOILERPLATE = frozenset(
    "activity repository summary total count this last week month day today yesterday "
    "there are were is was has have been recorded made merged added changed and "
    "with in the a an of only".split()
)


def contains_evaluator_instructions(text: str) -> bool:
    return _INSTRUCTIONS.search(text) is not None


def is_activity_only(text: str) -> bool:
    remainder, count = _ACTIVITY_METRIC.subn("", text)
    words = set(re.findall(r"\w+", remainder.lower()))
    return count > 0 and words <= _ACTIVITY_BOILERPLATE
