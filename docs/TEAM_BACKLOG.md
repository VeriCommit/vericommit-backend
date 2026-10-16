<p align="center">
  <img src="../images/vericommit-v-check-logo.png"
       alt="VeriCommit V Check Logo"
       width="180">
</p>

<h1 align="center">Team Backlog</h1>

<p align="center">
  <strong>Build | Integrate | Demonstrate</strong>
</p>

<p align="center">
  <img src="../images/VeriCommit Team Backlog Roadmap.png"
       alt="VeriCommit workflow from milestone proposal to human review"
       width="100%">
</p>

---


## Purpose

This backlog translates the VeriCommit MVP scope into actionable tasks for the hackathon team.

**Priority definitions**

- **P0:** Required for the end-to-end demo.
- **P1:** Important if time permits after the core demo works.
- **Future:** Outside the current MVP.

Task ownership below is proposed and should be confirmed by the team.

## Delivery Workflow

**Product alignment  Backend + Frontend  Integration & Testing  Demo**

- **Product lead:** Clarifies requirements and coordinates delivery.
- **Joshua (Backend):** Retrieves evidence and implements AI-assisted evaluation.
- **Wale (Frontend):** Builds milestone input and the evaluation report.
- **Together:** Integrate, test, and demonstrate the complete flow.

## P0  Required for the Demo

### 1. Agree on the API Contract

**Owners:** Joshua (backend) and Wale (frontend)  
**Support:** Product lead  
**Deliverable:** An agreed request and response schema documented in `docs/API_CONTRACT.md`.

Acceptance criteria:
- Both leads agree on the endpoint, request fields, and response fields.
- Criterion status values are consistent across backend and frontend.
- Error responses are defined.
- The team decides whether the first demo uses live GitHub evidence, sample evidence, or both.

### 2. Confirm the Milestone Data Model

**Owners:** Product lead and Joshua  
**Support:** Wale  
**Deliverable:** A clear definition of milestone fields and acceptance criteria.

Acceptance criteria:
- A milestone has a title, description, and acceptance criteria.
- Acceptance criteria are available to the evaluator.
- The team agrees how the repository URL and evidence source are represented.
- Milestone expectations are defined before evaluation.

### 3. Build the Milestone Input UI

**Owner:** Wale  
**Support:** Product lead  
**Deliverable:** A usable screen for entering the project, repository, milestone, and acceptance criteria.

Acceptance criteria:
- Required fields are clearly labelled.
- Invalid or incomplete input produces understandable feedback.
- The user can submit a valid milestone for evaluation.

### 4. Implement Evidence Input

**Owner:** Joshua  
**Support:** Product lead  
**Deliverable:** A backend workflow that supplies evidence for evaluation.

Acceptance criteria:
- The backend can accept the agreed evidence source.
- Live GitHub retrieval is used if feasible within the available time.
- Clearly labelled sample evidence is available as a fallback.
- Retrieval failures are reported rather than misrepresented as no project progress.
- Secrets are not exposed to the frontend or committed to Git.

### 5. Implement AI-Assisted Evaluation

**Owner:** Joshua  
**Support:** Product lead  
**Deliverable:** An evaluation that compares evidence against agreed acceptance criteria.

Acceptance criteria:
- Each criterion receives an agreed status.
- Findings are grounded in available evidence.
- Missing evidence and uncertainty are explained.
- The evaluator does not invent evidence or make final funding decisions.
- The response follows the agreed API contract.

### 6. Build the Evaluation Report UI

**Owner:** Wale  
**Support:** Product lead  
**Deliverable:** A report screen that presents the evaluation clearly.

Acceptance criteria:
- The report shows the milestone and acceptance criteria.
- Each criterion displays its status and explanation.
- Evidence links are visible when available.
- Missing evidence, uncertainty, and limitations are distinguishable.
- The report states that human review is required.

### 7. Integrate and Test the Complete Flow

**Owners:** Joshua and Wale  
**Support:** Product lead  
**Deliverable:** A working end-to-end demonstration.

Acceptance criteria:
- A user can enter a milestone.
- The application obtains live or clearly labelled sample evidence.
- The backend returns an evaluation.
- The frontend displays the report.
- Invalid input and evaluation failures are handled understandably.
- The team tests at least one case with supporting evidence and one with insufficient evidence.

### 8. Prepare the Demo and Product Walkthrough

**Owner:** Product lead  
**Support:** Joshua and Wale  
**Deliverable:** A concise presentation of the problem, workflow, results, limitations, and next steps.

Acceptance criteria:
- The demo explains the value for grantors and grantees.
- Sample data is clearly identified.
- The team demonstrates evidence and uncertainty rather than only an AI-generated summary.
- The final decision remains with the human reviewer.

## P1  If Time Permits

### 9. Improve Evidence Coverage

**Owners:** Joshua and Wale

- Add additional evidence types where practical.
- Improve loading, empty, and error states.
- Improve the readability of evidence references.

### 10. Improve Reviewer Experience

**Owner:** Wale  
**Support:** Product lead

- Make evidence gaps easy to understand.
- Improve report navigation and accessibility.
- Add a clear place to record or communicate the reviewer's decision if feasible.

### 11. Add Automated Tests

**Owners:** Joshua and Wale

- Test request validation and response structure.
- Test criterion-status handling.
- Test important UI states.
- Test the end-to-end workflow.

## Future  After the MVP

- Explore Stellar and Drips integrations.
- Investigate grant-payment integrations.
- Add broader grant administration capabilities.
- Explore multi-project and multi-grantor workflows.
- Evaluate deployment, security, privacy, and operating costs for production use.

## Working Agreements

- The API contract is proposed until Joshua and Wale agree on it.
- Changes to shared request or response structures must be communicated to both leads.
- Prioritize a complete, reliable demo over extra features.
- Keep sample evidence clearly labelled.
- Never commit API keys, access tokens, or other secrets.
- Use small, understandable changes and test important behavior.
- Use the VeriCommit commit-message convention: ` Short description of change`.

## Definition of Done

A task is done when its acceptance criteria are met, the relevant behavior has been checked, and any necessary documentation is updated.

