# API Contract  VeriCommit MVP

**Status:** Frontend-approved evaluation contract and domain alignment; backend lead confirmation and unresolved technical decisions remain pending before joint finalization.

The maintainer confirms that the frontend lead has approved both the evaluation contract and the intended domain-model alignment. No additional frontend reapproval is required for these documentation changes. Product approval of the domain specification is also confirmed. The evaluation interface remains unchanged.

| Approval | Current status |
|---|---|
| Frontend lead | Baseline and intended domain alignment approved; no additional reapproval required. |
| Backend lead | No explicit approval recorded; confirmation pending. |
| Domain specification | Officially approved, as confirmed by the maintainer. |
| Overall API contract | Frontend approval recorded; backend confirmation and unresolved technical decisions pending. |

## 1. Purpose

This document defines the proposed request and response between the VeriCommit frontend and backend for evaluating a software-project milestone.

The contract is intentionally small for the hackathon MVP. Both teams should agree on any changes before relying on the interface.

## 2. Evaluation Endpoint

- **Method:** `POST`
- **Path:** `/api/v1/evaluations`
- **Content-Type:** `application/json`

The endpoint evaluates available project evidence against previously agreed milestone acceptance criteria.

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

Suggested error codes:

- `INVALID_REQUEST`  required input is missing or invalid.
- `INVALID_REPOSITORY_URL`  repository URL is invalid or unsupported.
- `REPOSITORY_ACCESS_DENIED`  the application cannot access the repository.
- `EVIDENCE_RETRIEVAL_FAILED`  evidence could not be retrieved.
- `EVALUATION_FAILED`  evaluation could not be completed.

The frontend should display an understandable message and allow the user to recover where possible.

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

## 9. Implementation Agreement

Before implementation, Joshua and Wale should confirm:

1. The endpoint path and request fields.
2. The response schema and criterion status values.
3. How sample evidence is selected.
4. How errors are returned and displayed.
5. Whether the first demo uses live GitHub retrieval, sample evidence, or both.

Any agreed changes should be reflected in this document and communicated to both teams.

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
