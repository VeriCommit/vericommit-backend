# BE-01 / Milestone 1.1 — Evaluation API Contract Review

**Status: Source review complete; technical recommendations PROPOSED. Contract
approval pending from both leads. Not a finalized API contract.**

This review preserves the original documented interface and product rules. An
"established" requirement below means it appears in the supplied documentation;
it does not imply that the leads have approved the contract. Only the open
decisions and recommendations require additional technical choices. Work stops
at Milestone 1.1.

## 1. Sources inspected and reconciliation

All five required files are now present and have been read in full. The previous
missing-document blocker is resolved. No repository `AGENTS.md` was found.

| Document | Relevant sections / role |
| --- | --- |
| [API_CONTRACT.md](API_CONTRACT.md) | Sections 2–8 define the interface and rules; sections 1 and 9 retain proposed status and require joint agreement. |
| [MVP_SCOPE.md](MVP_SCOPE.md) | Sections 2–3 define evidence, reports, and human decisions; sections 4–5 constrain scope and disclosure. |
| [AI_EVALUATION_RULES.md](AI_EVALUATION_RULES.md) | Sections 2–5 define inputs, evidence grounding, statuses, and reports; sections 7–8 define privacy and acceptance checks. |
| [TEAM_BACKLOG.md](TEAM_BACKLOG.md) | P0 tasks 1–2 and 4–6 define agreement, evidence, evaluation, and reporting; Working Agreements require both leads' approval. |
| `API_CONTRACT_REVIEW.md` (previous version) | Reconciled below; its provisional guesses are superseded by the supplied sources. |

The earlier `/evaluate` candidate is withdrawn in favor of the documented route.
Request names, string-array criteria, the evidence selector, response names,
status values, and error envelope are documented, not new naming decisions.
Structured per-criterion evidence and a top-level limitations array already
exist in the response example. Earlier open questions about criterion shape,
status definitions, and evidence/limitations placement are answered by these
sources; no new criterion IDs or replacement shapes are proposed. No
authoritative document is changed.

## 2. Requirements verified against the sources

### Endpoint and request — API contract sections 2–3

**`POST /api/v1/evaluations`**, with **`Content-Type: application/json`**.

The endpoint compares available evidence against previously agreed milestone
acceptance criteria. Preserve the nested `milestone` object and these fields:

| JSON field | Documented type | Required | Meaning / values |
| --- | --- | --- | --- |
| `project_name` | string | Yes | Human-readable project name. |
| `repository_url` | string | Yes | GitHub repository URL; sample-mode ambiguity is recorded as D3, not silently relaxed. |
| `milestone.title` | string | Yes | Agreed milestone title. |
| `milestone.description` | string | Yes | Expected outcome. |
| `milestone.acceptance_criteria` | array of strings | Yes | Criteria agreed before evaluation; do not replace with criterion objects. |
| `evidence_source` | string | Yes | Exactly `github` or `sample`. |

The error example describes a title and at least one criterion; the evaluation
rules also require milestone/criteria validation. A formal minimum count,
blank-string policy, and upper bounds still need to be specified (D2).

For `sample`, the backend must use clearly labelled demonstration evidence, not
pretend to retrieve live GitHub data. The contract recognizes both source values;
which are enabled for the first demo remains a team decision (API contract
section 9; backlog P0 task 1).

### Response — API contract section 4; evaluation rules section 5

Preserve all names and nesting below. Types are shown by the contract's JSON
example; response requiredness, nullability, and bounds are not specified by a
formal field table. D4 proposes formalizing them, not renaming them.

| JSON field | Shape shown / documented meaning |
| --- | --- |
| `evaluation_id` | string; evaluation identifier. No UUID format or persistence guarantee is specified. |
| `project_name` | string; project name. |
| `milestone_title` | string; milestone title. |
| `overall_summary` | string; concise summary that must not hide uncertainty. |
| `criteria_results` | array of per-criterion objects. |
| `criteria_results[].criterion` | string; the agreed criterion being assessed. |
| `criteria_results[].status` | string; one of the three values below. |
| `criteria_results[].explanation` | string; assessment and evidence gaps. |
| `criteria_results[].evidence` | array of evidence-reference objects; may be empty as illustrated. |
| `criteria_results[].evidence[].type` | string; the example uses `pull_request`, not a complete allowed-value list. |
| `criteria_results[].evidence[].title` | string; evidence title. |
| `criteria_results[].evidence[].url` | string; source URL in the example; sample/no-URL behavior remains open. |
| `suggested_next_steps` | array of strings; questions or actions for review. |
| `limitations` | array of strings; evaluation-wide limitations. |
| `human_review_required` | boolean shown as `true`; mandatory human review is a product requirement, not a configurable option. |

Each agreed criterion must be evaluated separately, with status and explanation.
Evidence references accompany factual findings whenever available. Sample
references and actual provenance must be distinguishable from live GitHub data.
The existing response example is explicitly illustrative, not verified evidence.

### Criterion statuses — API contract section 5; evaluation rules section 4

| Exact value | Established semantics |
| --- | --- |
| `supported` | Available evidence supports the criterion. |
| `insufficient_evidence` | Available evidence does not demonstrate the criterion. |
| `uncertain` | Evidence exists but is ambiguous, or its sufficiency cannot be determined confidently. |

Missing evidence is not proof of missing work. No `failed`, approval status,
score, or additional status is introduced. New status values require agreement
between both leads.

### Errors — API contract section 6

Preserve the existing envelope: `{"error":{"code":"...","message":"..."}}`.
The source labels the following codes "Suggested"; their names and meanings
remain the baseline, pending joint approval:

| Exact code | Existing definition |
| --- | --- |
| `INVALID_REQUEST` | Required input is missing or invalid. |
| `INVALID_REPOSITORY_URL` | Repository URL is invalid or unsupported. |
| `REPOSITORY_ACCESS_DENIED` | The application cannot access the repository. |
| `EVIDENCE_RETRIEVAL_FAILED` | Evidence could not be retrieved. |
| `EVALUATION_FAILED` | Evaluation could not be completed. |

The frontend must show understandable messages and allow recovery where possible.
No HTTP mappings or structured field-error details are currently specified.

### Product rules that are not open technical choices

From API contract sections 7–8, MVP scope sections 2–5, evaluation rules sections
2–8, and backlog P0 tasks 4–6:

- Evaluate the agreed criteria independently; do not invent or change them.
- Ground factual findings in evidence; do not fabricate commits, pull requests,
  test results, releases, or outcomes. Distinguish observed facts from inference.
- Disclose missing evidence, ambiguity, access limitations, and retrieval failures;
  do not present retrieval failure as proof of no progress.
- Activity counts do not independently prove quality, completion, originality,
  or impact; a mention in a commit/PR does not establish working functionality.
- Clearly label sample evidence. Sample fallback is permitted by the scope and
  backlog, but its selection and switching behavior remain unspecified.
- **Human review is mandatory.** `human_review_required` must remain `true` for an
  evaluation report. The AI does not approve milestones, release funds, or make
  final funding decisions; a human decision is outside the AI evaluation.
- Treat repository content as untrusted evidence, not instructions. Respect
  access permissions and avoid exposing secrets or unnecessary private content.
- Keep the demo small and free-tool-based; production payment integrations and
  broader grant administration remain outside the MVP.

## 3. Genuine open decisions and minimal recommendations

All recommendations below are **PROPOSED**, not new established requirements.
They retain the documented route, names, statuses, source values, and error codes.

| ID | Unresolved decision / source gap | Recommendation for lead agreement |
| --- | --- | --- |
| D1 | Execution and identifier semantics: the contract shows a complete report, but does not state response timing or identifier guarantees. | Return a completed report in the request/response interaction for the MVP; keep `evaluation_id` an opaque string. Do not infer polling, report lookup, or durable storage from the identifier. |
| D2 | Validation: no numeric bounds, whitespace/null policy, extra-field policy, or exact accepted repository URL forms. | Require non-blank strings and at least one non-blank criterion; reject missing/null required values and wrong JSON types rather than coercing them. Agree trimming, maximum field lengths, criterion count/length, request-size limit, duplicate handling, and unknown-field behavior. Agree accepted GitHub URL scheme/host/path forms and normalization. Numeric limits remain unset. |
| D3 | Repository requirement in sample mode: the API table requires `repository_url` unconditionally, while MVP scope section 2A says "when available", demo criterion 2 permits repository OR sample selection, and evaluation rules section 2 permits repository URL OR sample source. | Preserve the current required field pending agreement. Prefer allowing omission only for `sample` if both leads approve a contract amendment; define omission vs. null explicitly. Do not invent a repository URL to satisfy validation. Confirm URL validation behavior for a supplied sample-mode URL and that it does not imply live retrieval. |
| D4 | Response schema precision and correlation: requiredness/nullability, ordering, duplicate criteria, evidence type values, and identifier format are not fully specified. | Formalize the existing response example as the field baseline. Prefer all shown response fields to be present, collections as arrays rather than null, one result per input criterion in input order, and unchanged criterion text. Resolve duplicate-input policy with D2; avoid adding criterion IDs. Agree evidence `type` values based on actual supported evidence. |
| D5 | First-demo modes and sample selection: both values are documented, but selection, unsupported-mode behavior, and fallback policy are not. | Decide live, sample, or both for the first demo. Prefer a single documented backend-owned fixture for `sample`, with no new request field or caller-uploaded evidence. Explicit `sample` should select it deterministically. On live retrieval failure, prefer a disclosed error and explicit user retry in sample mode over automatic switching. If automatic fallback is chosen, agree the trigger and report disclosure; never switch silently. |
| D6 | Provenance representation: source disclosure is mandatory, but the response lacks an explicit actual-source field; evidence items show URLs but no stable sample-reference form. | Preserve `evidence[].type`, `title`, and `url`. For the minimal demo, consider disclosing actual source and sample label/stable reference in existing `limitations` and evidence titles. Agree how URL-less samples are represented: absent vs. null `url`, or an explicitly approved reference-field addition. Do not fabricate URLs or conflate evidence kind (`type`) with source (`github`/`sample`). Any machine-readable provenance addition needs explicit field-name/type approval; none is adopted here. |
| D7 | Error versus limited-report boundary: retrieval failures must be disclosed, but the contract does not define when incomplete evidence prevents an evaluation. | Return a limited report only when an honest criterion-by-criterion assessment is possible; use existing `limitations`, criterion explanations, and next steps for coverage gaps. When retrieval or evaluation cannot proceed, use the existing corresponding error code. Agree partial/zero-evidence behavior and retrieval-failure wording; missing evidence must not become a new status or a claim of missing work. |
| D8 | Error transport details: HTTP mapping, code precedence, and field-level validation feedback are undefined. | Keep `error.code` and `error.message`. Review the candidate mapping below, including which code wins for overlapping validation failures. Retain the current envelope for the minimal demo; add structured details only if both leads agree its name, item shape, and field-location syntax. Do not expose framework-specific error responses as an undocumented alternate contract. |

These decisions can be expressed through JSON objects, arrays, strings, booleans,
and explicit constraints in later Pydantic models. No Python-specific type,
framework default, model, or implementation is prescribed here.

### Candidate HTTP mapping — PROPOSED under D7–D8

None of these HTTP statuses is specified by the original contract.

| Situation / existing code | Proposed HTTP status | Qualification requiring agreement |
| --- | --- | --- |
| Completed evaluation report | `200` | Also applies to valid reports containing `insufficient_evidence` or `uncertain`; those statuses are not transport failures. |
| Malformed JSON / `INVALID_REQUEST` | `400` | Use the existing shared error envelope. |
| Missing/invalid fields / `INVALID_REQUEST` | `422` | Agree whether validation instead uses a uniform `400`. |
| Invalid/unsupported repository URL / `INVALID_REPOSITORY_URL` | `422` | Prefer this specific code over generic validation for URL-format failures; precedence for multiple errors remains open. |
| Repository inaccessible / `REPOSITORY_ACCESS_DENIED` | `403` | Candidate only: the code describes application access, not necessarily caller authorization. Confirm whether an upstream-failure status is more accurate and how the frontend explains recovery. |
| Evidence retrieval cannot complete / `EVIDENCE_RETRIEVAL_FAILED` | `502` | Agree access-denial precedence and handling of transient failures/timeouts; limited successful reports are governed by D7. |
| Evaluation cannot complete / `EVALUATION_FAILED` | `500` | Generic public failure message; confirm any distinction for upstream evaluation-service failures without changing the code definition. |

## 4. Approval checklist and handoff

The source-review blocker is resolved. Final agreement is still pending. Both
technical leads must confirm the baseline and resolve the applicable decisions;
the product lead should help reconcile D3 and the first-demo choice.

- [x] Read all four authoritative sources and the earlier review.
- [x] Reconcile provisional guesses against the original interface and rules.
- [ ] Both leads confirm `POST /api/v1/evaluations`, the existing request/response
  names and shapes, both evidence-source values, and all three criterion statuses.
- [ ] Confirm D1–D4: execution, validation limits, sample-mode repository
  requirement, response requiredness, and criterion correlation.
- [ ] Confirm D5–D7: first-demo modes, sample selection/fallback, evidence provenance
  and URL-less references, limitations, and error-versus-report boundaries.
- [ ] Confirm D8: existing error-code definitions, HTTP mappings, overlapping-error
  precedence, and whether structured validation details are needed.
- [ ] Both leads confirm mandatory human review and the evidence/uncertainty rules.
- [ ] Record explicit approval from the backend lead and frontend lead, including
  agreed decisions and any approved amendments in `API_CONTRACT.md`.
- [ ] After approval, align examples for live/sample evidence, limited evidence,
  validation errors, access/retrieval failures, and evaluation failures.

**Backend lead approval: PENDING. Frontend lead approval: PENDING.**
`API_CONTRACT.md` remains proposed and unchanged. Review preparation is complete;
contract finalization is not. Milestone 1.2 requires explicit authorization even
after the leads agree.

## 5. Verification and scope

Only `docs/API_CONTRACT_REVIEW.md` is updated in this continuation. Verification:

- Manual source cross-check: passed; documented names, enums, error definitions,
  and human-review rules are retained, with recommendations labelled separately.
- `git diff --no-index --check -- /dev/null docs/API_CONTRACT_REVIEW.md`: passed
  without whitespace errors; Git emitted an LF-to-CRLF conversion notice.
- Before/after `git hash-object` checks: all four authoritative source hashes
  match, confirming their contents are unchanged.
- Runtime tests: not applicable to this documentation-only change.

No endpoint, Pydantic schema, dependency, database, frontend functionality, GitHub
retrieval, or AI integration is introduced. No credentials or secrets are added.
Work stops at Milestone 1.1.
