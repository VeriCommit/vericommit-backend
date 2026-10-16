# MVP Scope  VeriCommit

## 1. MVP Objective

Demonstrate that a grantor and grantee can agree on a software milestone, examine relevant GitHub evidence, generate an AI-assisted evaluation, and use the report to support a human review decision.

## 2. Must-Have Capabilities

### A. Milestone Definition
A user can enter:
- Project name
- Milestone title
- Milestone description
- Acceptance criteria
- Repository URL, when available

The milestone and its acceptance criteria must be visible to the evaluator.

### B. Evidence Input
The application can obtain relevant GitHub evidence, such as:
- Commit messages and links
- Pull requests and links
- Release information, when available

If live GitHub retrieval is unavailable or too costly in implementation time, the demo may use a small, clearly labelled sample dataset. Sample evidence must never be presented as live repository data.

### C. AI-Assisted Evaluation
The evaluator compares the available evidence against each agreed acceptance criterion and produces:
- A concise overall summary
- Evidence supporting progress
- Criteria with insufficient or missing evidence
- Uncertainties and limitations
- Suggested next steps or questions for review

Each factual finding should reference the evidence that supports it whenever possible.

### D. Review Report
The frontend presents the milestone, acceptance criteria, evidence links, findings, and uncertainties in a clear report.

The report must distinguish:
- Supported by available evidence
- Not demonstrated by available evidence
- Uncertain or requiring human verification

"Not demonstrated" does not necessarily mean the work was not done.

### E. Human Decision
The reviewer can inspect the report and record or communicate a decision outside the AI evaluation.

The AI does not approve milestones, release funds, or make final funding decisions.

## 3. End-to-End Demo Acceptance Criteria

The MVP is demo-ready when the team can:

1. Enter a milestone with explicit acceptance criteria.
2. Provide a repository or select clearly labelled sample evidence.
3. Run the evaluation workflow.
4. View a report that relates findings to the agreed criteria.
5. Inspect relevant evidence links or sample evidence references.
6. See missing evidence and uncertainty separately from supported findings.
7. Explain how a human reviewer reaches the final decision.

## 4. Out of Scope

- Automatic grant payments or fund release
- Production-grade grant management and accounting
- Production Stellar or Drips integration
- Claims that commit counts prove developer productivity
- Claims that repository activity alone proves originality, correctness, or real-world impact
- Complex multi-organization permission administration
- Paid APIs or services required for the core demo

## 5. Constraints

- Use free tools and services for the hackathon demo.
- Keep the implementation small enough to finish within the available time.
- Clearly disclose sample data and limitations.
- Do not expose GitHub tokens or other secrets in the frontend, logs, or repository.
- Respect repository access permissions.
- Agree on the frontend/backend API contract before both sides depend on it.

## 6. Suggested Build Order

1. Agree on the milestone data structure and evaluation report format.
2. Build the frontend with sample evidence and a sample report.
3. Implement the backend evaluation endpoint.
4. Add live GitHub evidence retrieval if feasible.
5. Connect the frontend to the backend.
6. Test the complete flow and prepare the demo.

## 7. MVP Success Definition

A reviewer can follow one milestone from agreed criteria through available evidence and AI-assisted evaluation to a human decision, while understanding what the evidence does and does not establish.
