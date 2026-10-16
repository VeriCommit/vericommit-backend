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

## Unresolved contract details

The technical recommendations in `docs/API_CONTRACT_REVIEW.md` D1–D8 remain
open except for the approved D6 URL-less sample-reference representation. This
schema keeps the contract's current fields. In particular:

- **D2:** Only `https://github.com/<owner>/<repo>` (with optional trailing slash)
  is accepted; the original string is preserved. Other URL forms and normalization
  require agreement. No length limits are imposed. Whitespace-only required strings
  and undocumented fields are rejected without rewriting input or deduplicating it.
- **D3:** `repository_url` is required in both modes as shown in the contract.
- **D4:** Response fields shown in the example are required; evidence and other
  collections may be empty. Evidence `type` is a string, not an invented enum.
  The models preserve list order; matching response criteria to a request remains
  an integration responsibility.
- **D6 — approved URL-less sample representation:** `EvidenceReference.url` must
  be present and accepts a nonblank string or `null`. Use `null` only for sample
  evidence with no genuine URL; clearly label the sample, and never invent a URL.
  Empty `evidence` lists remain valid as illustrated in the contract. Other D6
  questions, including machine-readable provenance, remain open.
- **D8:** The existing nested `error.code` and `error.message` shape is preserved.
  Error-code finalization, HTTP mappings, and optional field details remain open.

These implementation choices do not resolve other D1–D8 questions or declare
the shared contract jointly finalized.
D1 execution/identifier guarantees, D5 sample selection and fallback, and D7
limited-report/error boundaries also remain open and do not add schema fields.
