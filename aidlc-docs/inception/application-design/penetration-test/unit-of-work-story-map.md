# Penetration Test — Requirement-to-Unit Map

User Stories were skipped for this effort (execution plan: one persona, no user-facing feature, and the PT-FR and
PT-NFR items already serve as acceptance criteria). This file therefore maps **requirements** to units, which is the
role the story map plays in the project workflow. Every functional and non-functional requirement is owned by exactly
one unit; supporting units are listed where a requirement is delivered in steps.

## Functional requirements

| Requirement | Owner unit | Supporting units | Notes |
|---|---|---|---|
| PT-FR-1 Throwaway stack | U1 | U5 (teardown proof in the full run) | Amended 2026-11-22: no published ports. |
| PT-FR-2 Safety guard | U1 | U6 (its tests must pass before the live run) | Guard self-test runs before any request. |
| PT-FR-3 Synthetic data | U1 | | |
| PT-FR-4 Track A code audit | U4 | | Sub-agent protocol and caps from the execution plan. |
| PT-FR-5 Track B suite | U2 | U4 (adds proofs) | One module per area. |
| PT-FR-6 Scanners | U3 | | ZAP in-network, Trivy offline. |
| PT-FR-7 Findings register | U0 | U2, U3, U4 (write to it) | States, severity rule, strict expected-failure proofs. |
| PT-FR-8 Report | U5 | | Generated from the register and ledger. |
| PT-FR-9 One command and CI | U5 | U1, U2, U3 (each adds phases) | `pentest.yml` is hand-started only. |
| PT-FR-10 Live exposure check | U6 | | Own gate; announced before the run. |
| PT-FR-11 Fix stage | none | | Deliberately outside this plan; own plan after the report is read. |

## Non-functional requirements

| Requirement | Owner unit | Supporting units | How |
|---|---|---|---|
| PT-NFR-1 Live-system safety | U1 | U0 (leak check), U6 | Guard, linter, no real data; the only live contacts are Docker health status (local runs) and U6. |
| PT-NFR-2 Isolation | U1 | U2 (egress test), U3 (Trivy offline) | Internal network; isolation phase; tested, not assumed. |
| PT-NFR-3 Reproducibility | U5 | U1 (pins, deterministic seed) | Versions, digests and commit in the report. |
| PT-NFR-4 Bounded effort | U2 | U1 (phase limits), U3 (scan limits), U4 (run budget) | Fixed caps and time limits. |
| PT-NFR-5 Evidence quality | U0 | U4 (disproof, proofs) | The evidence rule is enforced by `confirm()` and the Validator. |
| PT-NFR-6 Maintainability | U0 | all | Own project, own dependency file, tests of the harness in ordinary CI. |
| PT-NFR-7 Disclosure order (A2) | U0 | U2, U4 | Validator requires the owner-notified date on high and critical findings. |
| PT-NFR-8 Process | all | | Branch and pull request per unit, audit and state updated, identity checked before every write. |

## Assumptions

| Assumption | Unit | Where it bites |
|---|---|---|
| A1 Sub-agents only for Track A, capped | U4 | Run budget; work packages without credentials; pause before wave 2. |
| A2 High or critical told to the owner before commit | U0 (check), U2, U4 (practice) | Validator field; I tell the owner in chat first. |
| A3 VPN peer treated as a network neighbour | U2 (containers and network, CORS), U4 (severity), U6 | Severity rating context. |
| A4 Helm chart tested statically | U3 (Trivy, rendered chart), U4 (review) | No cluster is created. |
| A5 One live exposure check | U6 | At most 20 requests, announced first. |
| A6 No product change or release | all | Application source is never edited by a pen-test unit. |

## Component assignment (each component built in exactly one unit)

| Component | Unit | Component | Unit |
|---|---|---|---|
| C1 Stack Manager | U1 | C8 Findings Register and Validator | U0 |
| C2 Compose Linter | U1 | C9 Audit Kit | U4 |
| C3 Request Guard | U1 | C10 Leak Check | U0 |
| C4 Synthetic Seed | U1 | C11 Report Generator | U5 |
| C5 Stub Server | U1 | C12 Run Orchestrator | U1 creates; U2, U3, U4, U5 each add their phases |
| C6 Track B Suite | U2 | C13 Live Exposure Check | U6 |
| C7 Scanner Adapters | U3 | | |

C12 is the one component that grows across units by design (decision U-D3).

## Validation

- [x] Every PT-FR and PT-NFR item has an owner unit, except PT-FR-11, which is out of this plan by decision.
- [x] Every component C1 to C13 is assigned (C12 as stated).
- [x] No dependency cycle (`unit-of-work-dependency.md`).
- [x] Every unit has a definition of done and its approval stops are listed (`unit-of-work.md`).
- [x] No real data, address, key or token appears in these documents.
