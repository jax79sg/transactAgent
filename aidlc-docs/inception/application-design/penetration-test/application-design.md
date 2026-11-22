# Application Design — Penetration Test (Consolidated)

Status: **approved 2026-11-22 ("approve")** at the Application Design gate. Nothing described here has been built.
Source documents: `components.md`, `component-methods.md`, `services.md`, `component-dependency.md` (this directory) and
`inception/plans/penetration-test-application-design-plan.md` (decisions D1 to D15, questions, answers).

## 1. Summary

A new top-level project, `pentest/`, with thirteen components. Twelve of them build, guard, run and report on a
throwaway copy of the application stack; the thirteenth is a separate, tiny script for the one allowed look at
the live deployment. The throwaway stack is one compose project of its own on an internal network with no route out
and **no published ports**; everything that tests it (the runner with a real browser, ZAP) is a container on that
network. Google, Gemini and model calls are answered by one stub container that takes the real hostnames and is
trusted through a throwaway certificate authority, so the application images stay untouched. Findings go through
one register whose validator will not accept `confirmed` without a failing proof against recorded, unmodified source.

## 2. Owner's answers to the design questions

| Question | Answer | Effect on the design |
|---|---|---|
| Q1 Stub for fixed Google and Gemini hostnames | **A** | One stub container, real names as network aliases, per-run throwaway certificate authority, application images untouched. A library that ignores the certificate setting falls back to "fails closed" and is reported as a limitation; the U1 spike decides which. |
| Q2 Real browser | **B** (not my recommendation, followed) | The runner is the official Playwright Python image, pinned by digest, with the harness added. Roughly 1.5 GB; **the exact reference, digest and size are stated to the owner before the first pull**. Its tag must match the Playwright version in the lockfile. |
| Q3 Protecting the live stack | **C** | Hard CPU, memory and process limits on every throwaway container; a pre-run check of the five live containers' Docker health and free memory; and **I ask the owner before each full local run**; a local run also needs an explicit quiet confirmation flag. CI skips the live checks. |
| Q4 Loopback ports | **A** | No ports published at all. Replaces the loopback-port wording of PT-FR-1 and ground rule 1; recorded as an amendment in the requirements (section 9) and the execution plan. |

## 3. Traceability to the requirements

| Requirement | Satisfied by |
|---|---|
| PT-FR-1 Throwaway stack | C1 Stack Manager, C2 Compose Linter (incl. parity check), C5 Stub Server; amended by Q4 = A |
| PT-FR-2 Safety guard | C3 Request Guard (allowlist, live denylist, synthetic marker, self-test), C2 Linter, D4 marker |
| PT-FR-3 Synthetic data | C4 Synthetic Seed |
| PT-FR-4 Track A | C9 Audit Kit, S3 Audit Service |
| PT-FR-5 Track B | C6 Track B Suite (areas listed in `components.md`), C5 stub scenarios for the model-facing paths, the Isolation phase for the egress proof |
| PT-FR-6 Scanners | C7 Scanner Adapters (ZAP in-network, Trivy offline), normaliser |
| PT-FR-7 Register | C8 Findings Register and Validator, S2 Evidence Service |
| PT-FR-8 Report | C11 Report Generator |
| PT-FR-9 One command and CI | C12 Run Orchestrator, S1 Run Service, D14 workflow |
| PT-FR-10 Live exposure check | C13 Live Exposure Check, S5 Live Check Service |
| PT-FR-11 Fix stage | Not designed here (execution plan: its own plan after the report is read) |
| PT-NFR-1 Live-system safety | C2, C3, D13; Q3 = C process rule; the only contact is C13 and Docker health status |
| PT-NFR-2 Isolation | internal network, no published ports, Isolation phase, Trivy `--network none` |
| PT-NFR-3 Reproducibility | pinned digests, deterministic seed, `RunMeta` records commit, source-clean flag, digests, tool versions |
| PT-NFR-4 Bounded effort | fixed caps in the suite, phase and overall time limits, `RunBudget` for sub-agents |
| PT-NFR-5 Evidence quality | S2 rules, disproof by another model, strict expected-failure proofs, funnel in the report |
| PT-NFR-6 Maintainability | own project with its own dependency file; `tests/` for the harness itself |
| PT-NFR-7 Disclosure order (A2) | Validator requires the owner-notified date on high and critical findings |
| PT-NFR-8 Process | S4 Hygiene Service; branch and pull request per unit; identity check before every write |

## 4. What is decided later (not open questions; each is assigned)

| Item | Decided in | Note |
|---|---|---|
| Which libraries honour the certificate setting (httpx, requests, httplib2, the Google client libraries) | U1 spike, Functional Design | Result and limitations go in the report. |
| CPU, memory and process limit values per container; free-memory threshold for the pre-run check | U1 Infrastructure Design | Chosen against this machine's Docker allocation. |
| Allowed differences in the parity check; the set of lookalike names in the guard self-test | U1 Functional Design | |
| Exact image references, digests and sizes (runner, ZAP, Trivy, PostgreSQL, Qdrant) | stated to the owner before each pull | Runner and ZAP are the large ones; Trivy's database refresh is a separate announced download. |
| ZAP flags (update checks off, scan scope, report format) | U3 Infrastructure Design, from the pinned image's `--help` | Not taken from memory. |
| Register schema fields, severity rubric, test catalogue and caps | Functional Design for U4 (schema), U2 (catalogue, caps) | |
| Normaliser mapping per scanner | Functional Design for U3 | |
| Workflow file details | U5 Infrastructure Design | `workflow_dispatch` only, no secrets. |

## 5. Design validation

- [x] Every PT-FR and PT-NFR item maps to at least one component or service (section 3).
- [x] No component depends on the Run Orchestrator; no dependency cycles (`component-dependency.md`).
- [x] The only contact with the live deployment is C13 (GET and OPTIONS, 20 requests, own gate) and Docker's health
      status on a local run; both are stated in the requirements or in the owner's answer to Q3.
- [x] The throwaway stack has one network, internal, and publishes nothing; Trivy has none.
- [x] The application images, code and compose file are unchanged by this design.
- [x] Diagrams validated (two Mermaid flowcharts, both `valid: true`) with text alternatives.
- [x] No real data, address, key or token appears in these documents.

## 6. Consequences for the next stages

- **Units Generation** confirms the six units and their order from the execution plan (U1, U2, U3, U6, U4, U5);
  components C1 to C5 and C12's preflight belong to U1; C6 to U2; C7 to U3; C13 to U6; C8 to C10 and the
  audit to U4; C11 and the rest of C12 and the workflow to U5. Units Generation will fix that mapping.
- **Functional Design** (U1 to U4) and **Infrastructure Design** (U1, U3, U5) proceed as in the execution plan.
- The pull request for the inception records is opened when Units Generation is approved.
