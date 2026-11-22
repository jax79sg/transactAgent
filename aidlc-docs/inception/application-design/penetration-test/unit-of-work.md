# Penetration Test — Units of Work

Source: `inception/plans/penetration-test-unit-of-work-plan.md` (approved 2026-11-22: Q1 A, Q2 B, Q3 A) and the
approved Application Design. Seven units, delivered in the order **U0, U1, U2, U3, U6, U4, U5**, then Build and Test.

Terminology: this is a brownfield addition, so a unit is a "module of work" inside one new project (`pentest/`), not
an independently deployable service. Each unit is one pull request.

## Code organisation

Everything is added; no product directory changes.

```
pentest/                             new, own pyproject.toml and uv.lock           (U0 creates)
  src/pentest/                       the library, one module per component
  tests/                             tests OF the harness (run in ordinary CI)
  suite/                             Track B tests AGAINST the stack                (U2)
  stack/                             compose project, runner / stub / seed images   (U1; ZAP and Trivy wiring U3)
  audit/                             PROCEDURE.md, ledger, work-package template    (U4)
  live_check.py                      the live exposure check                        (U6)
aidlc-docs/construction/pentest/     findings.json, ledger.json, REPORT.md          (U0 schema, U4 data, U5 report)
.github/workflows/test-pentest.yml   ordinary CI for pentest/tests                  (U0)
.github/workflows/pentest.yml        hand-started full run                          (U5)
```

## Branches and pull requests (stacked, Q2 = B)

Each unit's branch starts from the previous one and its pull request targets that branch. The repository merges
with merge commits, so the stack merges cleanly in order. Merging is the owner's call, one at a time.

| Order | Branch | Pull request targets |
|---|---|---|
| 0 | `docs/release-1.4.0-record` (PR #77, open) | `main` |
| 1 | `security/pentest-inception` (these records) | `docs/release-1.4.0-record` |
| 2 | `security/pentest-u0-evidence-core` | `security/pentest-inception` |
| 3 | `security/pentest-u1-harness-core` | `security/pentest-u0-evidence-core` |
| 4 | `security/pentest-u2-baseline-suite` | `security/pentest-u1-harness-core` |
| 5 | `security/pentest-u3-scanners` | `security/pentest-u2-baseline-suite` |
| 6 | `security/pentest-u6-live-check` | `security/pentest-u3-scanners` |
| 7 | `security/pentest-u4-code-audit` | `security/pentest-u6-live-check` |
| 8 | `security/pentest-u5-report-runner-ci` | `security/pentest-u4-code-audit` |

Every pull request body ends with the standard attribution line, and after each one I bind it and read its CI. The
auto-fix setting cannot be switched on for pull requests authored by the agent account; the owner can turn it on in
the pull request panel.

## Approval stops (Q3 = A: every stop, about 23)

| Unit | Stops |
|---|---|
| U0 | Functional Design; Code Generation plan; Code Generation (3) |
| U1 | Functional Design; Infrastructure Design; Code Generation plan; Code Generation (4) |
| U2 | Functional Design; Code Generation plan; Code Generation (3) |
| U3 | Functional Design; Infrastructure Design; Code Generation plan; Code Generation (4) |
| U6 | Code Generation plan; Code Generation (2) |
| U4 | Functional Design; Code Generation plan; Code Generation (3) |
| U5 | Infrastructure Design; Code Generation plan; Code Generation (3) |
| All | Build and Test (1) |

Extra stops from the owner's standing conditions (not workflow stages): before the first image pull; before each
scanner pull and the Trivy database refresh; before the one live check; after sub-agent wave 1; before committing a
finding rated high or critical; before each full local run.

---

## U0. Evidence core

**Purpose:** the record-keeping that everything else relies on, with no Docker and no contact with any target.

**Components:** project skeleton; C8 Findings Register and Validator; C10 Leak Check.

**Requirements:** PT-FR-7; PT-NFR-1 (leak), PT-NFR-5 (states and evidence rule), PT-NFR-6, PT-NFR-7 (A2 date check).

**Deliverables**
- `pentest/pyproject.toml`, `uv.lock`, package skeleton, shared types (`Phase`, `FindingState`, `Severity`, `Candidate`).
- The register schema and `Register` (load, save, add candidate, confirm, reject, note hardening, record owner notice,
  funnel); the Validator (schema, cited paths and lines exist, state rules, two-way test binding, A2 date).
- The Leak Check, with patterns read from a git-ignored local file and a clear fail-closed message when absent.
- `.github/workflows/test-pentest.yml` and the harness tests for all of the above.

**Done when:** the harness tests pass locally and in CI; the Validator rejects each way a record can be wrong (a test
per rule); `confirm()` refuses without a proof run; the Leak Check never prints matched text; leak scan clean.

**Design stages:** Functional Design (register schema, states, severity rubric, validator rules, leak-check rules);
Infrastructure Design skipped (no infrastructure).

**Risk:** low. Pure Python; nothing starts, pulls or contacts anything.

## U1. Harness core

**Purpose:** the safe throwaway stack and the two guards, with the first working slice of the one command.

**Components:** C1 Stack Manager; C2 Compose Linter; C3 Request Guard; C4 Synthetic Seed; C5 Stub Server; the first
phases of C12 (preflight, build, up, seed, isolation, teardown).

**Requirements:** PT-FR-1, PT-FR-2, PT-FR-3; PT-NFR-1, PT-NFR-2, PT-NFR-3.

**Deliverables**
- `pentest/stack/`: the compose project (internal network, named volumes, no `container_name`, no bind mounts, no
  published ports, limits on every service), the runner, stub and seed images.
- Linter with the safety rules and the parity check; Guard with allowlist, live denylist, marker check and self-test;
  Seed with every feature present; Stub Server with the scenario and request-log interface and the certificate
  authority; the U1 spike that shows which libraries honour the certificate setting.
- The orchestrator's preflight (linter, guard self-test, leak patterns present, live-container health and free memory,
  the quiet confirmation), build, up, seed, isolation proof and teardown; teardown leaves nothing behind.

**Done when:** the stack comes up from empty with migrations at the head; the guard refuses every live port and name
(tested); the isolation proof shows no route out; the stubbed hostnames resolve to the stub; teardown leaves no
container, volume or network; the harness tests pass; a first full local run succeeds **after the owner agrees to it**.

**Design stages:** Functional Design; Infrastructure Design.

**Owner stops:** exact reference, digest and size of the runner image (about 1.5 GB), PostgreSQL and Qdrant before
any pull; the first local run.

**Risk:** the highest of the build units. This is where a mistake could touch the live database. Mitigations are
the two guards, no bind mounts, no published ports, a separate project name, resource limits, the pre-run health
check, and asking before each local run.

## U2. Baseline Track B suite

**Purpose:** the executable penetration tests against the throwaway stack.

**Components:** C6 Track B Suite; the orchestrator's suite phase.

**Requirements:** PT-FR-5; PT-NFR-4.

**Deliverables:** one module per area (authentication, authorisation and object handling, input handling, CORS and
cross-site requests, error and information leakage, Drive connection, settings/backup/export, web app in a real
browser, containers and network (static), model-facing paths (stubs), bounded resource exhaustion, egress proof);
shared fixtures; the catalogue mapping each test to the OWASP API Security Top 10 and ASVS; the `finding` marker; the
fixed caps. Any weakness the baseline finds is recorded in the register as it is produced, with the A2 order for high
or critical.

**Done when:** every area has tests; open findings are strict expected failures; the suite gives identical results on
two consecutive runs; caps are enforced; the stack is healthy after the exhaustion tests; leak scan clean.

**Design stages:** Functional Design (catalogue, caps, mapping); Infrastructure Design skipped.

## U3. Scanners

**Purpose:** OWASP ZAP and Trivy, offline-safe, with their output in the register.

**Components:** C7 Scanner Adapters and normaliser; the orchestrator's scanner and normalise phases.

**Requirements:** PT-FR-6.

**Deliverables:** ZAP baseline and API scan on the internal network; Trivy offline over saved images, the repository
tree and the rendered Helm chart; the separate database-refresh step; the normaliser to `needs_validation` candidates.

**Done when:** both scanners run against the throwaway stack only; their output lands in the register; Trivy ran with
no network; the scan timings and tool versions are recorded.

**Design stages:** Functional Design (normaliser mapping); Infrastructure Design (images, ZAP flags verified against
the pinned image, Trivy refresh).

**Owner stops:** exact reference, digest and size before each scanner pull; Trivy's database refresh announced
separately.

## U6. Live exposure check

**Purpose:** the one small look at the live deployment from a neighbour's point of view.

**Components:** C13 Live Exposure Check.

**Requirements:** PT-FR-10; assumption A5.

**Deliverables:** `pentest/live_check.py` with its own gate (GET and OPTIONS, allowlisted paths, no credentials, at
most 20 requests, target supplied at run time); tests for the allowlist, the method rule, the credential rule and the
cap.

**Done when:** the gate tests pass; the script shares no code path with the Request Guard; one run is made **after
the guard's tests pass and the owner has been told it is about to run**; the result is summarised without real
addresses.

**Design stages:** none (Functional and Infrastructure Design skipped); Code Generation plan and Code Generation only.

## U4. Track A code audit

**Purpose:** the code audit with capped sub-agents, whose survivors become proofs in the suite.

**Components:** C9 Audit Kit; the audit run.

**Requirements:** PT-FR-4; assumption A1.

**Deliverables:** `PROCEDURE.md`; the coverage ledger and work-package format; the run-budget; reconnaissance notes;
wave 1 (at most 12 hunters), the pause and report, wave 2 (at most 6), disproof (at most 30 verifiers on a
different model), proof tests added to the suite, record verification (at most 4 runs); the populated register and
ledger.

**Done when:** the ledger is covered (shallow results marked shallow); every confirmed finding has a proof that fails
against the unmodified code; the Validator passes; the funnel is reported; sub-agent runs stayed within the caps.

**Design stages:** Functional Design (procedure, ledger, work-package format, budget rules); Infrastructure Design
skipped.

**Owner stops:** after wave 1 (runs used, approximate tokens, candidates; ask before wave 2); before committing any
finding rated high or critical.

**Risk:** cost and quality, not safety: sub-agents are read-only, get no credentials or live address, and the register
is written only by me.

## U5. Report, runner and CI

**Purpose:** turn the pieces into one command, one report and one hand-started workflow.

**Components:** C11 Report Generator; completion of C12 (report phase, exit statuses); the CI workflow.

**Requirements:** PT-FR-8, PT-FR-9; PT-NFR-3 (versions and digests in the report).

**Deliverables:** `REPORT.md` generator (method, scope, coverage, findings by severity, hardening notes, residual risk,
limitations, funnel, run metadata); the full orchestrator; `.github/workflows/pentest.yml` (`workflow_dispatch` only,
no secrets, fails on any unexpected failure or a new high or critical finding not in the register).

**Done when:** one command produces the report from a clean checkout; the workflow runs green on its branch; two
consecutive runs agree; the Report refuses to write if the Leak Check hits.

**Design stages:** Infrastructure Design (the workflow); Functional Design skipped.

## Build and Test (after U5)

Clean-checkout run of the harness tests, one full end-to-end local run (with the owner's yes), and one CI run; the
build-and-test instruction files under `aidlc-docs/construction/build-and-test/` are written for this effort.

## Not a unit: the fix stage

PT-FR-11 (triage and fixes) starts only after the owner has read the report and gets its own plan. No pen-test unit
edits product code.
