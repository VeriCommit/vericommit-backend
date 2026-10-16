# API Contract  VeriCommit MVP

**Status:** Approved MVP evaluation contract baseline; D1–D8 are resolved at the
policy level. Runtime implementation is deferred to the backend issues listed in
section 9.

**Final confirmation (2026-10-16):** The backend maintainer explicitly approves
the documented MVP policies and the D8 HTTP mappings, timeout handling, and error
precedence below. This records backend confirmation alongside the frontend lead's
previously recorded approval; it does not claim a new frontend review or approval
of additional fields, services, or grant-management functionality.

The maintainer confirms that the frontend lead has approved both the evaluation contract and the intended domain-model alignment. No additional frontend reapproval is required for these documentation changes. Product approval of the domain specification is also confirmed. The evaluation interface remains unchanged.

| Approval | Current status |
|---|---|
| Frontend lead | Baseline and intended domain alignment approved; no additional reapproval required. |
| Backend maintainer / backend confirmation | Explicit approval of the documented MVP policies and final D8 error policy recorded above. |
| Domain specification | Officially approved, as confirmed by the maintainer. |
| Overall API contract | Approved public MVP baseline: `POST /api/v1/evaluations`, sections 2–8 below, and the domain/MVP boundary in section 10. |

## 1. Purpose

This document defines the approved request and response between the VeriCommit frontend and backend for evaluating a software-project milestone.

The contract is intentionally small for the hackathon MVP. Future public interface changes require explicit agreement; this confirmation preserves the existing fields, source values, statuses, evidence URL nullability, error envelope, and human-review requirement.

## 2. Evaluation Endpoint

- **Method:** `POST`
- **Path:** `/api/v1/evaluations`
- **Content-Type:** `application/json`

The endpoint evaluates available project evidence against previously agreed milestone acceptance criteria.

### Approved MVP execution policy (D1)

Evaluation completes synchronously within the request/response interaction. Each
successful evaluation returns a unique, nonblank `evaluation_id` string. No UUID
format, background queue, polling route, or persistence is required. ID generation
and uniqueness are evaluation-service responsibilities; the schema validates the
required nonblank string, not uniqueness across evaluations. This policy does not
claim that an evaluation service or endpoint is already implemented.

## 3. Request

### Example

```json
{
  "project_name": "Community Tools",
  "repository_url": "https://github.com/example/community-tools",
  "milestone": {
    "title": "Implement member registration",
    "description": "Allow a new member to register and access the application.",
    "acceptance_criteria": [
      "A user can submit the registration form.",
      "Invalid input produces understandable validation errors.",
      "Automated tests cover successful and unsuccessful registration."
    ]
  },
  "evidence_source": "github"
}
```

### Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `project_name` | string | Yes | Human-readable project name |
| `repository_url` | string | Yes | GitHub repository URL |
| `milestone.title` | string | Yes | Agreed milestone title |
| `milestone.description` | string | Yes | Expected outcome |
| `milestone.acceptance_criteria` | string array | Yes | Criteria agreed before evaluation |
| `evidence_source` | string | Yes | `github` or `sample` |

For `evidence_source: "sample"`, the backend must use clearly labelled demonstration evidence rather than pretending to retrieve live GitHub data.

### Approved MVP request validation (D2)

The maintainer approves the existing strict Pydantic behavior as the MVP default:

- Reject missing required fields, null required values, wrong JSON types,
  whitespace-only required strings, and undocumented fields; do not coerce types.
- Require at least one acceptance criterion, with every criterion a nonblank
  string. Preserve wording, whitespace within nonblank strings, ordering, and
  duplicates exactly; do not trim, rewrite, or silently deduplicate criteria.
- Accept only `github` and `sample` as evidence-source values.
- Retain the implemented GitHub URL validator: HTTPS, a case-insensitive
  `github.com` host without credentials or an explicit port, and an owner/repository
  path with an optional trailing slash. Owner names begin/end with an ASCII
  alphanumeric character and otherwise contain alphanumerics or hyphens; repository
  names contain ASCII alphanumerics, underscores, dots, or hyphens and cannot be
  `.` or `..`. Reject query/fragment delimiters, whitespace, character codes below 32,
  and additional path segments. Preserve the supplied URL without normalization.
- Existing limits are a minimum of one criterion and nonblank required strings.
  No numeric maximum field length, criterion count/length, or request-size limit
  is currently imposed by these schemas; no new bounds are introduced here.

`repository_url` remains required in both modes under the current field table.
This is the confirmed D3 MVP limitation: sample mode still requires a valid
repository URL even though it does not fetch that repository. Do not invent a URL
to satisfy validation. Any future omission/null policy requires an explicit contract
amendment. Public field names and shapes are unchanged.

### Evidence mode and provenance policies (D5–D6)

Both approved selector values, `github` and `sample`, are supported by the contract.
GitHub retrieval failure must not silently substitute sample evidence. BE-05 owns
deterministic sample fixture selection; this policy does not implement a provider.

Preserve actual source information and stable references internally. Do not invent
URLs or source references, or add public provenance fields. Source disclosure is a
current interface limitation: evidence items have no dedicated public actual-source
field. Later evidence/report services must clearly disclose source and limitations
through existing titles and report limitations, without changing evidence `type`
into a source selector. A null URL alone is not a sample label.

## 4. Response

### Example

```json
{
  "evaluation_id": "eval_demo_001",
  "project_name": "Community Tools",
  "milestone_title": "Implement member registration",
  "overall_summary": "Some evidence supports progress, but not every acceptance criterion is demonstrated.",
  "criteria_results": [
    {
      "criterion": "A user can submit the registration form.",
      "status": "supported",
      "explanation": "A pull request describes the registration form implementation.",
      "evidence": [
        {
          "type": "pull_request",
          "title": "Add registration form",
          "url": "https://github.com/example/community-tools/pull/12"
        }
      ]
    },
    {
      "criterion": "Invalid input produces understandable validation errors.",
      "status": "insufficient_evidence",
      "explanation": "The available repository evidence does not demonstrate the validation behavior.",
      "evidence": []
    },
    {
      "criterion": "Automated tests cover successful and unsuccessful registration.",
      "status": "uncertain",
      "explanation": "Test-related changes are visible, but the available evidence does not establish that both scenarios are covered.",
      "evidence": []
    }
  ],
  "suggested_next_steps": [
    "Provide a demonstration or test result for invalid input.",
    "Review the registration tests for both success and failure cases."
  ],
  "limitations": [
    "Repository activity alone does not prove that the feature works in production."
  ],
  "human_review_required": true
}
```

The URLs and findings in this example are illustrative only; they are not verified project evidence.

### Evidence references without a genuine URL

`criteria_results[].evidence[].url` remains present in every evidence reference
and may be a string or `null`. Use a genuine URL for URL-bearing evidence. For
clearly labelled sample evidence with no genuine URL, use `"url": null` rather
than inventing a link. A `null` URL alone does not identify the source as sample;
sample evidence must still be clearly labelled.

Illustrative sample evidence reference (not verified project evidence):

```json
{
  "type": "test_result",
  "title": "Sample: registration validation test result (illustrative)",
  "url": null
}
```

## 5. Allowed Criterion Statuses

### Confirmed response policy (D4)

Preserve every response field and nesting shown above. All shown fields are
required; collections are arrays and may be empty, not null. Evidence `type`
remains a nonblank string rather than a new enum. Each result preserves the
original criterion wording and input order, including duplicate criteria; the
evaluation service owns runtime criterion/result correlation. Schemas preserve
list order but do not independently compare a response with its request.

`human_review_required` must be the literal boolean `true`, not numeric or string
equivalents. Do not add persistent project, Milestone, Grantor, Grantee, or Funding
Agreement identifiers. The present-but-nullable evidence `url` rule is unchanged.

- `supported`  available evidence supports the criterion.
- `insufficient_evidence`  available evidence does not demonstrate the criterion.
- `uncertain`  evidence exists, but its meaning or sufficiency is unclear.

The absence of evidence must not automatically be interpreted as proof that work was not done.

## 6. Error Responses

Use a consistent error structure.

### Example

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Provide a milestone title and at least one acceptance criterion."
  }
}
```

Approved public application error codes:

- `INVALID_REQUEST`  required input is missing or invalid.
- `INVALID_REPOSITORY_URL`  repository URL is invalid or unsupported.
- `REPOSITORY_ACCESS_DENIED`  the application cannot access the repository.
- `EVIDENCE_RETRIEVAL_FAILED`  evidence could not be retrieved.
- `EVALUATION_FAILED`  evaluation could not be completed.

The frontend should display an understandable message and allow the user to recover where possible.

### Reports versus errors (D7)

When retrieval succeeds but available evidence is genuinely insufficient, return
an honest limited report using the existing criterion statuses, explanations,
limitations, and next steps. Missing evidence is not proof of missing work.
When required evidence retrieval or AI evaluation fails, return the corresponding
error rather than presenting the failure as an empty successful retrieval or proof
that no work exists. Do not silently switch to sample evidence after a live failure.

### Approved error transport and selection policy (D8)

The confirmed error envelope remains `error.code` plus `error.message`, with no
additional public fields or codes. The maintainer approves these mappings for
BE-10's later FastAPI exception handlers; framework defaults do not override them:

| Outcome / code | Approved HTTP status |
| --- | --- |
| Completed evaluation, including an honest limited report | `200` |
| Malformed JSON / `INVALID_REQUEST` | `400` |
| Missing or invalid fields / `INVALID_REQUEST` | `400` |
| Unsupported or invalid repository URL / `INVALID_REPOSITORY_URL` | `400` |
| Repository access unavailable / `REPOSITORY_ACCESS_DENIED` | `403` |
| Required retrieval failed / `EVIDENCE_RETRIEVAL_FAILED` | `502` |
| Evaluation failed / `EVALUATION_FAILED` | `502` |
| Upstream evidence retrieval timeout / `EVIDENCE_RETRIEVAL_FAILED` | `504` |
| Upstream AI evaluation timeout / `EVALUATION_FAILED` | `504` |

An upstream timeout changes the HTTP status to `504`, retaining the code for the
failed operation. It does not introduce a timeout code or any response fields.

Select errors deterministically in this workflow order:

1. Validate incoming request fields and `evidence_source`.
2. Validate the repository URL (required in both evidence modes).
3. Resolve repository access and permissions when required by the selected source.
4. Retrieve evidence when required.
5. Perform the AI evaluation.
6. Return the contract-compliant report.

A failure at an earlier stage takes precedence: later stages must not run after
that failure. Within request validation, select the most specific applicable
documented code. If validation reports an invalid or unsupported repository URL,
use `INVALID_REPOSITORY_URL` rather than the generic `INVALID_REQUEST`, including
when the validation result also contains generic field errors. Malformed JSON,
missing required fields, and other field/source validation failures use
`INVALID_REQUEST`. This code-selection rule also applies when Pydantic detects URL
errors during request parsing; it does not authorize access, retrieval, or AI work
after a validation failure.

No automatic retry or fallback may disguise the original failure. In particular,
an access, retrieval, or AI failure must not be replaced by sample evidence or a
successful report. Explicit sample mode does not require live repository access
or retrieval. No exception handlers or structured field-error additions are
implemented by this documentation or by the Pydantic error-envelope models.

## 7. Evaluation Rules

- Evaluate evidence against the agreed acceptance criteria, not an invented definition of success.
- Include evidence links for factual findings whenever available.
- Do not invent commits, pull requests, test results, or release information.
- Do not treat commit count as a measure of quality.
- Distinguish missing evidence from missing work.
- Make uncertainty and technical limitations visible.
- Require a human reviewer to make the final milestone or funding decision.

## 8. Security and Privacy

- Never expose GitHub access tokens in frontend code or API responses.
- Do not request private-repository access unless it is necessary and authorized.
- Validate repository URLs and all incoming request fields.
- Do not log secrets or unnecessary private repository content.
- Clearly disclose whether evidence came from GitHub or sample data.

## 9. Final Agreement and Implementation Boundary

The approved baseline is the interface in sections 2–8, constrained by section 10.
The frontend lead's existing approval and the backend maintainer's explicit policy
and D8 approval finalize this MVP contract. D1–D8 are resolved as documented, not
as evidence that the full workflow exists. See
[the final review confirmation](API_CONTRACT_REVIEW.md#9-final-contract-confirmation-and-be-01-assessment)
for the individual policy statuses and BE-01 acceptance assessment.

BE-01 provides tested Pydantic request, response, evidence, criterion, and nested
error models. The error models validate the envelope and nonblank code/message
strings; they do not select a public code or HTTP status. Only the five approved
codes above may be emitted by the future runtime implementation. The schemas do
not prove evidence authenticity, sample labelling, source provenance, or correlation
of a response to its request.

| Later issue | Runtime responsibility, not implemented by BE-01 |
| --- | --- |
| BE-03 (#4) | FastAPI endpoint, request parsing/validation integration, and evaluation-service boundary. |
| BE-04 (#5) / BE-06 (#7) | Internal evidence normalization/provenance and authorized live GitHub retrieval. No public provenance fields are added. |
| BE-05 (#6) | Deterministic sample fixture/provider selection and explicit sample labels. |
| BE-07 (#8) | Synchronous AI evaluation, unique evaluation ID generation, criterion wording/order/correlation, and provider-failure handling. |
| BE-08 (#9) / BE-09 (#10) | Evidence-grounding validation and report assembly, genuine references, source/limitation disclosure, uncertainty, and mandatory human review. |
| BE-10 (#11) | Centralized error handlers, approved code/HTTP mapping and precedence, timeouts, and safe failure disclosure. |

Fixture content, provider internals, and runtime checks remain implementation work
within these policies. New public fields, provenance serialization extensions, or
relationship-management behavior require separately approved contract changes.

## 10. Domain Model Alignment

Relationship rules follow [VeriCommit Entity Relationships](domain-model/ENTITY_RELATIONSHIPS.md)
(`docs/domain-model/ENTITY_RELATIONSHIPS.md`), particularly sections 2, 4–9.
Product approval is confirmed by the maintainer for this review; the supplied
source still carries proposed-status wording. Specification approval must not be
interpreted as evidence that these rules or deferred workflows are implemented.

### Approved relationship rules

- Every persistent Milestone belongs to **exactly one Funding Agreement at a time**. Each
  Funding Agreement has **exactly one responsible Grantor entity and one Grantee**.
- A Grantor may fund multiple Grantees through separate Funding Agreements. Each
  agreement may define multiple Milestones with its own scope and criteria.
- A Grantee may have multiple active Funding Agreements with different Grantors
  simultaneously, including concurrent funding for different Milestones. The
  single-Grantor restriction applies to each agreement, not to the Grantee as a whole.
- A formally defined **Collaborative Grantor** represents multiple organizations
  acting as **one Grantor entity** for the relevant agreement. Independent Grantors
  do not automatically become collaborative because they fund the same Grantee
  or project. A single Milestone must not be assigned simultaneously to multiple
  independent Grantor entities; joint funding requires a formal Collaborative
  Grantor, or distinct Milestones under separate agreements as applicable.
- Grantor–Grantee relationships are mediated by Funding Agreements. Milestones and
  responsibilities are not implicitly shared across agreements. Sequential funding
  is permitted, not mandatory; later agreements must not rewrite earlier history.
- Scope and acceptance-criteria changes require authorization and preserved change
  history. An approved Milestone must not be moved directly to another agreement;
  any authorized correction or reassignment must preserve its original record,
  relationship history, evidence, evaluations, and human decisions.
- Transferring a Funding Agreement to another responsible Grantor requires explicit
  authorization, Grantee acknowledgement, and an audit trail recording the former
  and new Grantors, authorization, effective date, and reason. Historical evaluations
  and decisions remain traceable to the Milestone, agreement, and responsible
  Grantor applicable when they were made.
- Private terms, budgets, correspondence, and evidence do not become visible to
  other Grantors merely because they fund the same Grantee. Cross-funder access
  must be explicitly authorized and scoped.

### Current MVP evaluation boundary

`POST /api/v1/evaluations` remains the existing milestone-evaluation interaction.
All request/response fields, `github`/`sample` source values, criterion statuses,
error codes, and examples above are preserved. The submitted milestone and agreed
criteria describe the scope to evaluate; they are not a complete Funding Agreement
or ownership record. This endpoint does not create, transfer, or manage Funding
Agreements, and the request does not establish or change persistent Milestone
ownership. `project_name` and `repository_url` must not be treated as
Grantor, Grantee, or Funding Agreement identifiers, or as authorization to share
evidence across agreements.

No `grantor_id`, `grantee_id`, `funding_agreement_id`, or other relationship fields
are added to this payload. How a future implementation resolves agreement identity,
permissions, and historical associations requires a separately reviewed contract
extension; this endpoint does not claim to persist or enforce those relationships.
Full Funding Agreement lifecycle management, authorized transfers, and Milestone
correction/reassignment workflows are deferred beyond the MVP. No lifecycle
statuses, ownership-change operations, or funding/payment behavior are introduced here.

The evaluator remains evidence-grounded and assesses only the agreed criteria.
It cannot approve funding or change agreement ownership. Final milestone and
funding decisions remain human responsibilities, with `human_review_required: true`.
