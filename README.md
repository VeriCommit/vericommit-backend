# VeriCommit backend schemas (BE-01 Milestone 1.2)

Requires Python 3.12+. Install and check the schemas with:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

`src/vericommit_backend/schemas.py` models the JSON request, response, and error
shapes in `docs/API_CONTRACT.md`. No endpoint, evidence provider, funding-agreement
storage, or AI service is implemented here. `repository_url` remains required and
validated as a GitHub repository URL for both `github` and `sample`; sample mode
does not imply live retrieval. Model validation cannot establish that an evidence
URL is genuine, that a report is grounded in evidence, or that a criterion result
matches a particular request; those checks belong to later services.

## Confirmed MVP defaults and implementation boundaries

The maintainer has confirmed D1–D8 MVP policy defaults; HTTP mappings remain
proposals. See sections 7–8 of
`docs/API_CONTRACT_REVIEW.md`. The schema keeps the contract's current fields:

- **D1 — approved:** Evaluation is synchronous and successful responses require a
  unique nonblank `evaluation_id`. No queue, UUID format, or persistence is required.
  The schema checks nonblank IDs; future service code must generate unique IDs.
- **D2 — approved:** Retain strict validation and the existing GitHub URL validator,
  including an optional trailing slash and preservation of the original string.
  Required strings must be nonblank, types must match, extra fields are rejected,
  and criteria must contain at least one nonblank string. Wording, order, and
  duplicates are preserved. No numeric maximum lengths/counts/request-size bounds
  are imposed by the schemas. Exact URL rules are in `docs/API_CONTRACT.md` section 3.
- **D3 — confirmed MVP limitation:** `repository_url` is required in both modes.
- **D4:** Response fields shown in the example are required; evidence and other
  collections may be empty. Evidence `type` is a string, not an invented enum.
  The models preserve list order; matching response criteria to a request remains
  an integration responsibility.
- **D6 — approved URL-less sample representation:** `EvidenceReference.url` must
  be present and accepts a nonblank string or `null`. Use `null` only for sample
  evidence with no genuine URL; clearly label the sample, and never invent a URL.
  Empty `evidence` lists remain valid as illustrated in the contract. Actual-source
  disclosure is a later service responsibility; no public provenance fields are added.
- **D8:** The existing nested `error.code` and `error.message` shape is preserved.
  Error-code finalization, HTTP mappings, and precedence await confirmation;
  additional public error fields are not approved.

Later services must implement D5's deterministic fixture selection without silent
fallback, D6's actual-source preservation/disclosure through existing fields, and
D7's distinction between insufficient evidence and retrieval/evaluation failures.
No additional public error or provenance fields are approved. BE-10 owns exception
handlers; transport mappings and overlapping-error precedence await confirmation.
These policies do not declare joint contract finalization. Synchronous execution,
ID uniqueness, and criterion/result correlation are service requirements, not claims
of existing runtime functionality.
