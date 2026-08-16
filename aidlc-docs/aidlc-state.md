# AI-DLC State Tracking

## Project Information
- **Project Type**: Greenfield
- **Start Date**: 2026-07-31T12:04:15Z
- **Current Stage**: COMPLETE (OPERATIONS is a placeholder phase)

## Workspace State
- **Existing Code**: No
- **Reverse Engineering Needed**: No
- **Workspace Root**: /Volumes/1TB/projects/transactAgent

## Code Location Rules
- **Application Code**: Workspace root (NEVER in aidlc-docs/)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See code-generation.md Critical Rules

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | No | Requirements Analysis |
| Property-Based Testing | Partial (pure functions / serialization round-trips only) | Requirements Analysis |
| Resiliency Baseline | No | Requirements Analysis |

## Stage Progress
### 🔵 INCEPTION PHASE
- [x] Workspace Detection — Complete (2026-07-31T12:04:15Z)
- [x] Requirements Analysis — Complete & Approved (2026-08-01)
- [x] User Stories — Complete & Approved (2026-08-01, personas.md: 1 persona; stories.md: 5 epics / 24 stories)
- [x] Workflow Planning — Complete & Approved (2026-08-01)
- [x] Application Design — Complete & Approved (2026-08-01; 2 services: API Service + Ingestion Worker Service, sharing 1 DB, plus Frontend SPA; 12 components)
- [x] Units Generation — Complete & Approved (2026-08-01; 4 units: Database, API Service, Ingestion Worker Service, Frontend SPA; monorepo)

## INCEPTION PHASE: COMPLETE

### 🟢 CONSTRUCTION PHASE (per-unit loop)
Build order: Unit 1 Database -> Unit 2 API Service / Unit 3 Ingestion Worker Service -> Unit 4 Frontend SPA

#### Unit 1: Database
- [x] Functional Design — Complete & Approved (2026-08-01; 8 entities, 13 business rules, 4 state machines)
- [x] NFR Requirements — Complete & Approved (2026-08-01; PostgreSQL 16, Alembic, SQLAlchemy; Python 3.12+ locked in project-wide)
- [x] NFR Design — Complete & Approved (2026-08-01; auto-migrate w/ advisory lock, no separate broker)
- [x] Infrastructure Design — Complete & Approved (2026-08-01; postgres:16-alpine, bind mount, internal-only, healthcheck)
- [x] Code Generation — Complete & Approved (2026-08-01)

**UNIT 1: COMPLETE** (models.py patched 2026-08-01 during Unit 2 Code Generation — see audit.md: fixed a cross-cutting enum-storage bug found by actually running Unit 2's test suite; Unit 1's own 12 tests re-verified passing after the fix)

#### Unit 2: API Service
- [x] Functional Design — Complete & Approved (2026-08-01; JWT auth, 5 components' business logic, 10 API rules, DTOs)
- [x] NFR Requirements — Complete & Approved (2026-08-01; FastAPI, Uvicorn, Pydantic v2, PyJWT+passlib)
- [x] NFR Design — Complete & Approved (2026-08-01; CORS restricted, JWT dependency, /health, fail-fast migration)
- [x] Infrastructure Design — Complete & Approved (2026-08-01; port 7878, /health, corrected shared topology diagram)
- [x] Code Generation — Complete & Approved (2026-08-01; 41 tests passing, 3 real bugs found+fixed via actual execution)

**UNIT 2: COMPLETE**

#### Unit 3: Ingestion Worker Service
- [x] Functional Design — Complete & Approved (2026-08-01; Gemini extraction, OpenRouter categorization fallback, rapidfuzz similarity, statement-printed-SGD priority)
- [x] NFR Requirements — Complete & Approved (2026-08-01; Gemini+OpenRouter, rapidfuzz, Hypothesis; retroactively added OAuthCredential to Unit 1 + drive_connect to Unit 2, both re-verified passing)
- [x] NFR Design — Complete & Approved (2026-08-01; retry-with-backoff, 5 logical components)
- [x] Infrastructure Design — Complete & Approved (2026-08-01; no host port, file-based heartbeat healthcheck)
- [x] Code Generation — Complete & Approved (2026-08-01; 45/45 tests passing, 3 real bugs found+fixed via actual execution, 2 further design gaps caught+fixed)

**UNIT 3: COMPLETE**

#### Unit 4: Frontend SPA
- [x] Functional Design — Complete & Approved (2026-08-01; 5-page structure, sessionStorage, inline correction, URL-driven filter state)
- [x] NFR Requirements — Complete & Approved (2026-08-01; React, Tailwind+Radix, Chart.js, TanStack Query, fast-check)
- [x] NFR Design — Complete & Approved (2026-08-01; runtime config file, error boundary, 4 logical components)
- [x] Infrastructure Design — Complete & Approved (2026-08-01; port 8787, nginx multi-stage build, full topology finalized)
- [x] Code Generation — Complete & Approved (2026-08-01; 12/12 tests passing, 5 real bugs found+fixed via actual execution)

**UNIT 4: COMPLETE**

## ALL UNITS COMPLETE (2026-08-01)
Total: 12 (Database) + 46 (API Service) + 45 (Ingestion Worker) + 12 (Frontend) = 115 tests passing.

### Build and Test (after all units)
- [x] Build and Test — Complete (2026-08-01; full stack actually built + started + verified end-to-end; 115/115 unit tests + 4/4 integration scenarios passing; 2 more real bugs found+fixed via live containers — see build-and-test-summary.md for the full 13-bug list across the whole project)

## CONSTRUCTION PHASE: COMPLETE & APPROVED (2026-08-01)

## PROJECT STATUS: COMPLETE
(OPERATIONS phase is a placeholder per common/process-overview.md — deployment is docker-compose up, already covered in CONSTRUCTION.)

---

## Post-Completion Change: Recategorization Review Panel

Tracked separately from the original build above (base project status unchanged: COMPLETE). Artifacts use feature-scoped filenames so the original project-wide requirements/state history is preserved untouched.

- [x] Requirements Analysis — Complete & Approved (2026-08-02; `aidlc-docs/inception/requirements/recategorization-review-requirements.md`; 10 FRs, 4 NFRs; broadened sweep scope + hybrid auto-apply/review split resolved via one documented assumption)
- [x] User Stories — Complete & Approved (2026-08-02; `aidlc-docs/inception/user-stories/recategorization-review-stories.md`; Epic 6, 6 stories, US-6.1–US-6.6; personas.md unchanged; page named "Review" per flagged assumption)
- [x] Workflow Planning — Complete & Approved (2026-08-02; `aidlc-docs/inception/plans/recategorization-review-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP, per-unit NFR Requirements/Design + Infrastructure Design SKIP, Code Generation + Build and Test ALWAYS; sequence Database → {Ingestion Worker, API Service} → Frontend)
- [x] Application Design — Complete & Approved (2026-08-02; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new Recategorization Review component in API Service; Categorization Engine extended; ASCII diagram width-verified after edit)

## INCEPTION PHASE (this feature): COMPLETE
- [ ] Construction (per affected unit: database, ingestion-worker, api-service, frontend) — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-02; `domain-entities.md` +RecategorizationProposal, `business-rules.md` BR-14..16, `business-logic-model.md` +status lifecycle)
  - [x] Database — Code Generation: Complete & Approved (2026-08-02; `models.py` +RecategorizationProposal, migration `0004_recategorization_proposals.py`, `test_models.py` +TestRecategorizationProposal 4 tests, 16/16 unit tests passing, migration live-verified against real Postgres incl. upgrade/downgrade/idempotent-reupgrade)

**UNIT: DATABASE — COMPLETE (for this feature)**
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-02; WR-9/WR-10 added to `business-rules.md`, addenda to `business-logic-model.md`/`domain-entities.md`)
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-02; `config.py` +threshold, `categorization/repository.py` +2 functions, `categorization/service.py` broadened, `pipeline.py` call-site update, 5 new/1 corrected test, 72/72 unit tests passing)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature)**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-02; AR-11..13 added, `ProposalDTO`+5 DTOs, Recategorization Review Component logic in `business-logic-model.md`)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-02; new `recategorization/` module, 6 endpoints, `errors.py` +ProposalNotPendingError, `main.py` router registration, 18 new tests, 87/87 api-service unit tests passing, OpenAPI schema smoke-tested)

**UNIT: API SERVICE — COMPLETE (for this feature)**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-02; ReviewPage/ProposalTable/BulkActionBar + NavBar badge added to `frontend-components.md`; polling/selection-state logic added to `business-logic-model.md`)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-02; new `recategorization.ts` api client, `ReviewPage.tsx`, `NavBar.tsx` badge, `/review` route, 11 new tests, 47/47 frontend tests passing, clean `tsc`+`vite build`)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**
**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**

- [x] Build and Test — Complete (2026-08-02; `aidlc-docs/construction/build-and-test/recategorization-review-build-and-test-summary.md`; full stack rebuilt + redeployed, migration 0004 live-verified, real end-to-end flow verified against the live worker/API/frontend with isolated cleaned-up test fixtures, 1 real bug found and fixed [stale relationship in approve response] + 1 pre-existing out-of-scope bug flagged; 222/222 unit tests passing across all 4 units)

## CONSTRUCTION PHASE (this feature): COMPLETE

## FEATURE STATUS: COMPLETE — Recategorization Review Panel (Epic 6)

---

## Post-Completion Change: Nightly Transaction Backup to CSV

Tracked separately from the original build and from Epic 6 (base project status unchanged: COMPLETE). Feature-scoped filenames used.

- [x] Requirements Analysis — Complete & Approved (2026-08-08; `aidlc-docs/inception/requirements/nightly-backup-requirements.md`; 11 FRs, 4 NFRs; 2 rounds of clarifying questions resolved backup destination [separate dedicated Drive folder, not same-folder subfolder], retention semantics, missed-schedule catch-up, failure/notification behavior, and frontend panel placement on the Review page)
- [x] User Stories — Complete & Approved (2026-08-08; `aidlc-docs/inception/user-stories/nightly-backup-stories.md`; Epic 7, 4 stories US-7.1..7.4; personas.md unchanged, single existing persona reused)
- [x] Workflow Planning — Complete & Approved (2026-08-08; `aidlc-docs/inception/plans/nightly-backup-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP, per-unit NFR Requirements/Design + Infrastructure Design SKIP, Code Generation + Build and Test ALWAYS; sequence Database → {Ingestion Worker Service, API Service} → Frontend SPA)
- [x] Application Design — Complete & Approved (2026-08-08; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new Backup Manager Component (Ingestion Worker) + Backup Status Component (API Service); Drive Connector Component extended with upload/create-folder/list/delete; ASCII diagram width-verified after edit)

## INCEPTION PHASE (this feature): COMPLETE
- [ ] Construction (per affected unit: database, ingestion-worker, api-service, frontend) — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-08; `domain-entities.md` +BackupRun, `business-rules.md` BR-17..18, `business-logic-model.md` +write-once lifecycle explanation)
  - [x] Database — Code Generation: Complete & Approved (2026-08-08; `models.py` +BackupRun/BackupRunOutcome/BackupRunFailureCategory, migration `0006_backup_runs.py`, `test_models.py` +TestBackupRun 6 tests, 24/24 unit tests passing, migration live-verified against real Postgres incl. upgrade/downgrade/idempotent-reupgrade; found+flagged pre-existing out-of-scope bug in migration 0005 against a fresh DB, spawned as separate task, not fixed here)

**UNIT: DATABASE — COMPLETE (for this feature)**
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-08; WR-11..15 added to `business-rules.md`, new Backup Manager Component section + Drive Connector addendum in `business-logic-model.md`, `domain-entities.md` addendum)
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-08; new `backup/` package [`repository.py`, `service.py`], `clients/drive_client.py` +4 methods, `config.py` +3 settings, `main.py` poll_once() third branch, 133/133 unit tests passing)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature)**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-08; AR-14 added, `BackupStatusResponse` DTO, Backup Status Component logic in `business-logic-model.md`)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-08; new `backup/` module [`repository.py`, `service.py`, `schemas.py`, `router.py`], `main.py` router registration, `GET /backups/status`, 8 new tests, 113/113 api-service unit tests passing, OpenAPI schema smoke-tested)

**UNIT: API SERVICE — COMPLETE (for this feature)**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-08; BackupStatusPanel addendum in `frontend-components.md`, polling-interval reasoning in `business-logic-model.md`)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-08; new `api/backup.ts`, `types.ts` +BackupStatusResponse, `BackupStatusPanel` inline in `ReviewPage.tsx`, 5 new tests, 68/68 frontend tests passing, clean `tsc`+`vite build`)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**
**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**

- [x] Build and Test — Complete (2026-08-08; `aidlc-docs/construction/build-and-test/nightly-backup-build-and-test-summary.md`; full stack rebuilt + redeployed, migration 0006 live-verified, genuine live end-to-end verification against the real connected Google Drive account per explicit user confirmation [real backup upload, real retention deletion, real API status, real browser session] with full artifact cleanup afterward; 2 real bugs found and fixed [Drive OAuth scope too narrow for writes; no UI path to re-grant consent]; 1 pre-existing out-of-scope migration bug found and flagged, not fixed; 340/340 unit tests passing across all 4 units)

## CONSTRUCTION PHASE (this feature): COMPLETE

## FEATURE STATUS: COMPLETE — Nightly Transaction Backup (Epic 7)

---

## Post-Completion Change: Recurring Payments, Budget Alerts & Subscription Detection (Epic 8)

Tracked separately (base project status unchanged: COMPLETE). Feature-scoped filenames used. Working on git branch `feature/recurring-payments-budget-alerts` (created off `main` per user request, for easy rollback). No real payee names/amounts in any doc — user's real reference list stayed in chat only (public repo).

- [x] Requirements Analysis — Complete & Approved (2026-08-08; `aidlc-docs/inception/requirements/recurring-payments-requirements.md`; 14 FRs, 4 NFRs; 1 round of 9 questions + 1 targeted follow-up, all resolved — user granted standing blanket approval for stage-completion gates on this feature too)
- [x] User Stories — Complete & Approved (2026-08-08; `aidlc-docs/inception/user-stories/recurring-payments-stories.md`; Epic 8, 7 stories US-8.1..8.7; personas.md unchanged, single existing persona reused)
- [x] Workflow Planning — Complete & Approved (2026-08-08; `aidlc-docs/inception/plans/recurring-payments-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP, per-unit NFR Requirements/Design + Infrastructure Design SKIP, Code Generation + Build and Test ALWAYS; sequence Database → {Ingestion Worker Service, API Service} → Frontend SPA)
- [x] Application Design — Complete & Approved (2026-08-08; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new Recurring Payment Manager Component (Ingestion Worker) + Recurring Payments Component (API Service); Categorization Engine's similarity matcher reused, not duplicated; ASCII diagram width-verified after edit)

## INCEPTION PHASE (Epic 8): COMPLETE
- [ ] Construction (per affected unit: database, ingestion-worker, api-service, frontend) — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-08; `domain-entities.md` +RecurringPayment/RecurringPaymentMatch/DetectionSuggestion, `business-rules.md` BR-19..23, `business-logic-model.md` +match lifecycle +is_trusted lifecycle)
  - [x] Database — Code Generation: Complete & Approved (2026-08-08; `models.py` +3 entities/3 enums, migration `0007_recurring_payments.py`, `test_models.py` +15 tests, 40/40 unit tests passing, migration live-verified against real Postgres incl. upgrade/downgrade/idempotent-reupgrade)

**UNIT: DATABASE — COMPLETE (for Epic 8)**
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-08; WR-16..19 added to `business-rules.md`, new Recurring Payment Manager Component section + Categorization Engine addendum in `business-logic-model.md`, `domain-entities.md` addendum; due/overdue status computation explicitly deferred to API Service)
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-08; new `recurring_payments/` package [`cycle.py`, `repository.py`, `service.py`], `similarity.py` +public `amounts_in_range`, `pipeline.py`/`main.py` wiring, 168/168 unit tests passing; retroactive Database addition [`DetectionScanRun`]; real case-sensitivity matching bug found+fixed)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for Epic 8)**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-08; AR-15..20 added, 7 new DTOs, Recurring Payments Component logic in `business-logic-model.md`; status computation flagged as a necessary second implementation of the Worker's cycle-math, since the two services share no code)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-08; new `recurring_payments/` module [`cycle.py`, `repository.py`, `service.py`, `schemas.py`, `router.py`], 12 new endpoints, 3 new errors, 168/168 api-service unit tests passing, OpenAPI schema smoke-tested; status model refined from 3 to 4 states + status algorithm corrected during implementation)

**UNIT: API SERVICE — COMPLETE (for Epic 8)**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-08; Recurring Payments Dashboard-tab addendum in `frontend-components.md`, badge/invalidation reasoning in `business-logic-model.md`)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-08; new `api/recurringPayments.ts`, `types.ts` +12 DTOs, `NavBar.tsx` +RecurringPaymentsBadge, `DashboardPage.tsx` +4th "Recurring Payments" tab, 11 new tests [3 NavBar + 8 DashboardPage], 81/81 frontend tests passing, clean `tsc`+`vite build`; 2 test-only bugs found+fixed [TanStack Query v5 mutationFn 2nd-arg assertion mismatch; mock-restore-before-beforeEach test-isolation bug], no application code affected)

**UNIT: FRONTEND SPA — COMPLETE (for Epic 8)**

**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**

## CONSTRUCTION PHASE (Epic 8): COMPLETE

- [x] Build and Test — Complete (2026-08-08; `aidlc-docs/construction/build-and-test/recurring-payments-build-and-test-summary.md`; full stack rebuilt and redeployed against the live running project [`docker compose build/up`], migrations 0007/0008 auto-applied to the real database via the app's own advisory-lock startup path — verified via `alembic_version`; 460 unit tests passing across all 4 units [40 Database + 168 Ingestion Worker + 171 API Service + 81 Frontend], zero regressions; live E2E verification against the real running stack using invented placeholder recurring payments only [never the user's real list], incl. a real, unprompted detection scan against the full real transaction history correctly identifying genuine recurring patterns; one real bug found+fixed [bulk-import's AR-19 per-row isolation was bypassed by FastAPI's own request-body validation on a malformed amount/due-day — fixed by typing `BulkImportRow`'s numeric-ish fields as raw strings, parsed and validated per-row in the service layer instead], fix re-verified live through the actual browser UI, all placeholder test data cleaned up afterward)

**Recurring Payments, Budget Alerts & Subscription Detection (Epic 8): COMPLETE** — on branch `feature/recurring-payments-budget-alerts`, not yet merged to `main`.

---

## Post-Completion Change: Similarity-Matching Normalization for Reference-Code Noise

Tracked separately (base project status unchanged: COMPLETE). Feature-scoped filenames used. Continuing on
git branch `feature/recurring-payments-budget-alerts`. Unrelated in scope to Epic 8 but touches the same
`similarity.py` module (only `find_best_match`/`token_sort_ratio` scoring — Epic 8 only reuses
`amounts_in_range`, unaffected).

- [x] Requirements Analysis — Complete & Approved (2026-08-11; `aidlc-docs/inception/requirements/similarity-matching-requirements.md`; 7 FRs, 3 NFRs; 1 round of 6 questions, all answered; one apparent tension between answers [Q1 general/bank-agnostic vs Q5 conservative] reconciled and documented as Assumption #1, flagged for user correction at review if wrong)
- [x] User Stories — Skipped (2026-08-11; pure internal accuracy fix, no new user-facing feature/workflow)
- [x] Workflow Planning — Complete & Approved (2026-08-11; `aidlc-docs/inception/plans/similarity-matching-execution-plan.md`; Application Design SKIP, Units Generation SKIP, per-unit [Ingestion Worker Service only] Functional Design EXECUTE, NFR Requirements/Design + Infrastructure Design SKIP, Code Generation + Build and Test ALWAYS; single-unit change, Database/API Service/Frontend SPA untouched)

## INCEPTION PHASE (this change): COMPLETE
- [ ] Construction (Ingestion Worker Service unit only) — pending
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-11; WR-20 added to `business-rules.md`, addendum to `business-logic-model.md`'s Categorization Engine section; normalization pattern designed and live-validated against `rapidfuzz` — all 3 diagnosis examples now score 100.0 as same-payee pairs [up from the reported 81.7], AXS false-positive regression and CCY-conversion small-value regression both confirmed unaffected; `domain-entities.md` unchanged, no new/modified entity)

  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-11; `similarity.py` +`normalize_reference_noise`, `find_best_match` normalizes both sides; `test_similarity.py` +11 tests [7 direct normalization tests incl. 2 Hypothesis property tests, 4 `find_best_match` regression tests]; 179/179 unit tests passing [up from 168], zero regressions incl. AXS false-positive and CCY-conversion small-value tests; live diagnosis-example scores confirmed: NEO EMPIRE/WARBURG VENDING pairs now 100.0 [up from reported 81.7], cross-payee sanity check stays at 46.96)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature) — proceeding to Build and Test**

**ALL UNITS COMPLETE (for this feature — only the Ingestion Worker Service unit was affected)**

## CONSTRUCTION PHASE (this feature): COMPLETE

- [x] Build and Test — Complete (2026-08-11; `aidlc-docs/construction/build-and-test/similarity-matching-build-and-test-summary.md`; `ingestion-worker` Docker image rebuilt + redeployed, container healthy; 179/179 unit tests passing; live in-container verification via `docker compose exec` reproducing the original NEO EMPIRE scenario — match found, score 100.0, up from the originally reported 81.7; no historical re-scan triggered, forward-only per FR-6; no integration/e2e/performance/contract tests needed — no API/DB/UI surface touched)

## FEATURE STATUS: COMPLETE — Similarity-Matching Normalization for Reference-Code Noise

---

## Post-Completion Change: Local Embedding-Based Semantic Similarity

Tracked separately (base project status unchanged: COMPLETE; Similarity-Matching Normalization above also
COMPLETE). Continuing on git branch `feature/recurring-payments-budget-alerts`. Layered on top of, and
possibly replacing/complementing, the just-shipped WR-20 fix — relationship to be resolved via clarifying
questions, not assumed.

- [x] Requirements Analysis — Complete & Approved (2026-08-11; `aidlc-docs/inception/requirements/embedding-similarity-requirements.md`; 11 FRs, 5 NFRs; 10-question round + 2 rounds of clarification — runtime identified as real product "oMLX" via WebSearch verification [not a scam domain], then a deployment-topology ambiguity it exposed [macOS-native, cannot containerize] resolved as a user-managed external endpoint, config-pointed; embedding-first with fuzzy-text/WR-20 fallback, applied across Categorization Engine + Recurring Payment Manager + Detection Scan; badge = processing-status only, not match-found; async/eventually-consistent; one-time historical backfill [explicit departure from this project's forward-only precedent]; AXS amount-gate protection explicitly carried over as a hard NFR, not weakened)

- [x] User Stories — Complete & Approved (2026-08-11; `aidlc-docs/inception/user-stories/embedding-similarity-stories.md`; Epic 9, 5 stories US-9.1..9.5; personas.md unchanged, single existing persona reused; assessment: Execute=Yes, new user-facing badge + complex cross-cutting business logic)

- [x] Workflow Planning — Complete & Approved (2026-08-11; `aidlc-docs/inception/plans/embedding-similarity-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP; per-unit Functional Design EXECUTE for all 4 units; NFR Requirements/Design + Infrastructure Design EXECUTE for Ingestion Worker Service only, SKIP elsewhere; Code Generation + Build and Test ALWAYS; sequence Database → {Ingestion Worker Service, API Service} → Frontend SPA; Risk: Medium-High)

- [x] Application Design — Complete & Approved (2026-08-11; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; 2 new Ingestion Worker Service components [Vector Store Client, Embedding Manager]; extended Categorization Engine + Recurring Payment Manager [embedding-first, fuzzy-text fallback]; Transaction Management Component + Frontend SPA extended for the badge; new `transactions.embedding_status` field + separate Vector DB datastore [Worker-only access]; fifth `poll_once()` branch; key design resolution documented: query-time transient embedding vs. storage-time async/batched embedding are two distinct operations, resolving the apparent FR-3/FR-6 tension; ASCII diagram width-verified after edit)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Build order: Database → {Ingestion Worker Service, API Service} → Frontend SPA
- [ ] Construction — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-11; `domain-entities.md` +`Transaction.embedding_status`, `business-rules.md` BR-24, `business-logic-model.md` +lifecycle; no new entity, single field, no open questions)
  - [x] Database — Code Generation: Complete, awaiting review (2026-08-11; `models.py` +`EmbeddingStatus` enum +`Transaction.embedding_status`, migration `0009_transaction_embedding_status.py`, `test_models.py` +`TestTransactionEmbeddingStatus` 2 tests, 44/44 unit tests passing; migration live-verified against real Postgres incl. upgrade/downgrade/idempotent-reupgrade, all 6142 existing transactions backfilled to `pending` via server_default alone; 1 real bug found+fixed [`create_type` kwarg misplacement] via live execution, not unit tests)

**UNIT: DATABASE — COMPLETE (for this feature)**
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-13; blanket approval; new `embedding/` package [client.py, vector_store.py, similarity.py, repository.py, service.py]; integrated into categorization/service.py, recurring_payments/service.py, main.py; retroactive Database addition `RecurringPayment.embedding_status` [BR-25, migration 0010]; 3 real design gaps found+fixed during implementation and corrected in business-rules.md/business-logic-model.md/Application Design docs [runDetectionScan doesn't call find_best_match at all — redesigned as an additive embedding group-merge pass; fuzzy/embedding score-scale mismatch — rescaled to 0-100; matchNewTransaction's per-payment fallback needed whole-operation semantics]; qdrant-client API verified live against a real temporary Qdrant container [query_points not deprecated search, UUID string point IDs]; `docker compose build ingestion-worker` verified clean; 233/233 unit tests passing [up from 179]; full live rebuild/redeploy/migration verification deferred to this feature's Build and Test stage)
  - [x] Ingestion Worker Service — Infrastructure Design: Complete & Approved (2026-08-13; blanket approval; new `vector-db` docker-compose service [qdrant/qdrant, no host port, bind-mounted volume]; found+fixed a real issue by actually pulling the image: it has neither wget nor curl, switched healthcheck to a bash /dev/tcp check; ingestion-worker gains QDRANT_*/EMBEDDING_* env vars + non-blocking depends_on; docker-compose.yml and .env.example updated directly)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature) — proceeding to API Service**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-13; blanket approval; AR-21 `embeddingStatus` read-only exposure on `TransactionDTO`; AR-22 `RecurringPayment.embedding_status` reset-to-pending on create/name-changing-update — closes the write-path gap flagged during Ingestion Worker Code Generation, Database `BR-25`)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-13; blanket approval; `TransactionDTO` +`embedding_status` [3 construction sites updated together — transactions/router.py, recategorization/router.py, recurring_payments/service.py]; `update_recurring_payment` resets `embedding_status` to `pending` only on a `name`-changing update; `RecurringPaymentDTO` deliberately does not expose `embedding_status` [no UI purpose]; 4 new tests; 175/175 passing [up from 171]; OpenAPI schema smoke-tested [37 paths]; `docker compose build api-service` verified clean)

**UNIT: API SERVICE — COMPLETE (for this feature) — proceeding to Frontend SPA**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-13; blanket approval; small quiet per-row badge inline in TransactionRow's Description cell reflecting `embeddingStatus`, no new column/component/polling — deliberately not competing for attention with the actionable nav badges)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-13; blanket approval; `types.ts` +`embeddingStatus`; new `EmbeddingStatusBadge` inline in `TransactionRow`; found+fixed the field being required across 5 test-file mock-transaction construction sites before running anything [grepped `conversionUnavailable:` as a reliable anchor]; 2 new tests; 83/83 passing [up from 81]; clean `tsc -b` + `vite build`; `docker compose build frontend` verified clean)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**

**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**
  - [x] Ingestion Worker Service — NFR Design: Complete & Approved (2026-08-13; blanket approval; new no-retry/immediate-soft-fail resilience pattern [diverges from retry-with-backoff on purpose, FR-10], non-blocking Vector Store startup, 2 new logical components [EmbeddingClient, VectorStoreClient])
  - [x] Ingestion Worker Service — NFR Requirements: Complete & Approved (2026-08-13; blanket approval; Vector DB = Qdrant, embedding endpoint config kept separate from the existing categorization-LLM oMLX config, no-retry/soft-fail policy, tunables EMBEDDING_SIMILARITY_THRESHOLD/TOP_K/BATCH_SIZE/DIMENSIONS)
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-13; blanket approval granted to continue through all remaining stages of this feature). Question 1 answered A [retroactive Database addition, unified poll mechanism]. Retroactively added `RecurringPayment.embedding_status` + Database `BR-25` + lifecycle section [Database unit, `domain-entities.md`/`business-rules.md`/`business-logic-model.md`]; corrected 3 Application Design docs [`components.md`, `component-methods.md`, `services.md`] where the original Epic 9 addenda were incomplete/imprecise (RecurringPayment backlog not covered by the poll-cycle due-check; `runDetectionScan`'s collection-targeting conflated with `matchNewTransaction`'s). Added WR-21..26 to `business-rules.md`; added Vector Store Client + Embedding Manager component sections plus addenda to Categorization Engine/Recurring Payment Manager sections in `business-logic-model.md`; added `Vector`/`EmbeddingUnavailable` transient DTOs to `domain-entities.md`)

## CONSTRUCTION PHASE (Local Embedding-Based Semantic Similarity, Epic 9): COMPLETE

- [x] Build and Test — Complete (2026-08-13; `aidlc-docs/construction/build-and-test/embedding-similarity-build-and-test-summary.md`; full stack rebuilt+redeployed via `docker compose up -d --build` against the real live stack [6142 real transactions, 14 real recurring payments]; migration 0010 live-verified [alembic_version=0010, both tables backfilled to pending]; new `vector-db` service healthy, both Qdrant collections confirmed created with size=768/Cosine via the live worker; graceful degradation with `EMBEDDING_BASE_URL` unset confirmed live over multiple poll cycles, zero errors; `GET /transactions` confirmed live returning `embeddingStatus`; AR-22 confirmed live in both directions [rename resets to pending; non-rename update leaves it untouched] using an invented placeholder payment, deleted afterward with zero leftover test data; frontend bundle confirmed shipping the badge's markup/testid; 538/538 unit tests passing across all 4 units [47+233+175+83]; real-embedding-endpoint happy path and browser-visual checks explicitly deferred — noted, not silently skipped)

**Local Embedding-Based Semantic Similarity (Epic 9): COMPLETE** — on branch `feature/recurring-payments-budget-alerts`, not yet merged to `main`.

---

## Post-Completion Change: Matching Precision Refinement

Tracked separately (base project status unchanged: COMPLETE; Epic 9 above also COMPLETE). Continuing on git
branch `feature/recurring-payments-budget-alerts`. A direct follow-up refinement to Epic 9 — changes when the
LLM classifier runs, what text gets embedded, matching thresholds/scoring, and adds a new disagreement-review
surface reusing the Epic 6 Review page pattern.

- [x] Requirements Analysis — Complete & Approved (2026-08-16; `aidlc-docs/inception/requirements/matching-precision-refinement-requirements.md`; 12 FRs, 5 NFRs; 1 round of 8 questions + 1 round of 2 clarifications, all resolved — LLM now classifies every transaction always [same local server, `OPENROUTER_MODEL` changed, concurrent calls]; price-bucket added to embedded text [configurable buckets, existing rows re-embedded]; `embedding_similarity_threshold` raised [exact value deferred to Code Generation]; LLM category used as a soft score-boost signal during matching [applies to both categorization and recurring-payment matching]; a genuine category disagreement [both signals confident, differ] becomes a new two-candidate reviewable item on the existing `/review` page, not a bare `UNSURE` transaction; exact schema for carrying two candidate categories deferred to Application Design)
- [x] User Stories — Skipped (2026-08-16; approved by user — backend algorithm/matching refinement, no new user-facing workflow beyond the Review-page extension already captured directly in requirements FR-MPR-10/11)
- [x] Workflow Planning — Complete & Approved (2026-08-16; `aidlc-docs/inception/plans/matching-precision-refinement-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP, per-unit NFR Requirements/NFR Design/Infrastructure Design SKIP, Functional Design + Code Generation EXECUTE per unit, Build and Test ALWAYS; sequence Database → {Ingestion Worker Service, API Service} → Frontend SPA; Risk: Medium; user granted blanket approval for remaining stage-completion gates on this feature)
- [x] Application Design — Complete & Approved (2026-08-16; `aidlc-docs/inception/plans/matching-precision-refinement-application-design-plan.md`; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new `CategorizationDisagreement` entity [deliberately not an extension of `RecategorizationProposal`] + new `Transaction.llm_suggested_category_id` field; Categorization Engine gains `classifyBatch` [concurrent, called upfront per-file by the Ingestion Orchestrator] and `categorize()`'s signature/decision logic changes; Recategorization Review Component (API Service) extended with disagreement list/resolve/reject, no bulk actions; ASCII diagram width-verified programmatically after edit)

## INCEPTION PHASE (this change): further stages pending

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Build order: Database → {Ingestion Worker Service, API Service} → Frontend SPA
- [ ] Construction — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-16; `domain-entities.md` +`CategorizationDisagreement` entity +`Transaction.llm_suggested_category_id` field, `business-rules.md` BR-26..27, `business-logic-model.md` +`CategorizationDisagreement.status` lifecycle +`Transaction.category_source` addendum)
  - [x] Database — Code Generation: Complete & Approved (2026-08-16; `models.py` +`CategorizationDisagreement`/`CategorizationDisagreementStatus` +`Transaction.llm_suggested_category_id`, migration `0011_categorization_disagreements.py`, `test_models.py` +`TestTransactionLlmSuggestedCategory`/`TestCategorizationDisagreement` [5 tests], 52/52 unit tests passing [up from 47]; migration live-verified against the real running Postgres [copied into `transactagent-api` container, `alembic upgrade head`/`downgrade -1`/re-`upgrade head`, all clean; schema confirmed via `psql`; all 6142 real existing transactions confirmed `llm_suggested_category_id IS NULL` as expected; API container's `/health` unaffected throughout]

**UNIT: DATABASE — COMPLETE (for this feature)**
  - [x] Database — retroactive addition: migration `0012_reembed_after_price_bucket_text_change.py` (2026-08-16, during Ingestion Worker Functional Design, WR-32) — one-time data migration resetting all `completed` `embedding_status` rows back to `pending` so the existing poll mechanism re-embeds them with the new price-bucket text; no-op downgrade by design (see migration docstring)
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-16; `business-rules.md` WR-27..32, `business-logic-model.md` +`classifyBatch`/`categorize()` decision-logic addenda to Categorization Engine + boost addendum to Recurring Payment Manager, `domain-entities.md` +`DisagreementInfo` +`CategorizationResult` fields)
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-16; `config.py` +5 settings [`embedding_similarity_threshold` 0.75→0.82, `llm_classification_concurrency`, `embedding_price_bucket_boundaries`, `embedding_llm_agreement_boost`]; new `embedding/text.py` [`price_bucket_label`/`build_embedding_text`]; `categorization/service.py` +`classify_batch` [concurrent, deduped, `ThreadPoolExecutor`], `categorize()` signature/decision-logic rewrite [WR-28], `find_similar_transaction_via_embedding` +boost param, `recategorize_unsure_from_precedent`'s `_find_match` +boost; `categorization/repository.py` +`record_disagreement`; `orchestrator/pipeline.py` +upfront per-file `classify_batch` call, `_persist_transaction` +`llm_suggested_category_id` write +disagreement recording after flush; `embedding/service.py` + `recurring_payments/service.py` both switched to price-bucketed embedding text, `recurring_payments/service.py`'s embedding candidate search restructured to return raw scores [not a pre-filtered set] so the boost can be applied per-candidate; `.env.example` +4 new/changed vars; 19 new tests [`TestClassifyBatch` 4, `TestCategorize` disagreement/abstain branches +2, embedding-boost tests +2, `test_embedding_text.py` 9 new, recurring-payments boost tests +2], 252/252 unit tests passing [up from 233]; `docker compose build ingestion-worker` verified clean; full live rebuild/redeploy + migration application deferred to this feature's Build and Test stage)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature)**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-16; `business-rules.md` AR-23..27, `business-logic-model.md` Recategorization Review Component addendum, `domain-entities.md` +`DisagreementDTO`/`DisagreementPage`/`ResolveDisagreementRequest`)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-16; `errors.py` +`DisagreementNotPendingError`/`InvalidResolutionCategoryError`; `recategorization/repository.py` +3 disagreement query functions; `recategorization/service.py` +`list_pending_disagreements`/`resolve_disagreement`/`reject_disagreement`, `get_pending_count` now sums proposals+disagreements; `recategorization/schemas.py` +3 DTOs; `recategorization/router.py` +3 endpoints [`GET /recategorization/disagreements`, `POST .../resolve`, `POST .../reject`]; 16 new tests [8 service-layer, 8 endpoint-level], 191/191 unit tests passing [up from 175]; OpenAPI schema smoke-tested [40 paths, up from 37]; `docker compose build api-service` verified clean)

**UNIT: API SERVICE — COMPLETE (for this feature)**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-16; `frontend-components.md` +`DisagreementTable`/`DisagreementRow` addendum — a second, visually-separate table on the Review page, same convention `BackupStatusPanel` established; no bulk actions, per Application Design Decision 2)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-16; `types.ts` +`DisagreementDTO`/`DisagreementPage`/`DisagreementStatus`; `api/recategorization.ts` +`listPendingDisagreements`/`resolveDisagreement`/`rejectDisagreement`; new `DisagreementTable` component inline in `ReviewPage.tsx` [own query/mutations/invalidation, renders nothing when empty, two "Use X" buttons + Reject, no checkbox/select-all]; `ReviewPage.test.tsx` +1 `beforeEach` default mock [so pre-existing proposal-focused tests are unaffected by the new always-on query] +7 new tests; 90/90 frontend tests passing [up from 83]; clean `tsc -b`+`vite build` [ran inside a `node:20-alpine` container after finding no local Node install]; `docker compose build frontend` verified clean)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**

**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**

## CONSTRUCTION PHASE (Matching Precision Refinement): COMPLETE

- [x] Build and Test — Complete (2026-08-16; `aidlc-docs/construction/build-and-test/matching-precision-refinement-build-and-test-summary.md`; full stack rebuilt + redeployed via `docker compose build`/`up -d --build` against the real live stack [6142 real transactions, 14 real recurring payments, 122 real pending proposals]; migrations 0011/0012 auto-applied and live-verified [schema shape via `psql \d`, data-reset backlog watched draining live from 0/6142 to 6142/6142 `completed`]; **mid-Build-and-Test design change**: live-testing against the user's real oMLX server (`gemma-4-26b-a4b-it-4bit`) surfaced a real concern with the original one-HTTP-call-per-description design — reworked `classify_batch` into a two-phase batched-prompt-then-individual-fallback design [batch size 10, concurrency 5, both configurable], per 3 new clarifying decisions; `matching-precision-refinement-requirements.md` [new Post-Approval Change section, FR-MPR-3 revised], Ingestion Worker `business-rules.md` [WR-27 revised], and the Application Design plan [Key Design Resolution 2 revised] all updated in place; new `openrouter_client.classify_descriptions_batch`/`llm_classifier.classify_batch_prompt`/`config.py` +`llm_classification_batch_size`; 16 new/reworked tests [new `test_llm_classifier.py` 11 tests, `test_openrouter_client.py` +2, `TestClassifyBatch` reworked +3 net], 268/268 ingestion-worker tests passing [up from 252]; live-verified against the real running oMLX server at 3 separate checkpoints [6-item single batch 1.04s, 12-item chunked `classify_batch` 2.52s using the real live category whitelist, final 3-item check against the rebuilt+redeployed image], all correctly classified; survived an unrelated mid-session Docker/oMLX host restart with zero data loss [bind-mounted volumes confirmed intact, re-embed backlog resumed and completed cleanly]; API Service live-verified with a real minted JWT [`GET /recategorization/disagreements`, pending-count, full resolve flow using an invented placeholder transaction+disagreement, `category_source='llm'` write-through confirmed, all placeholder rows deleted afterward with zero leftovers]; Frontend `docker compose build` clean, live-deployed bundle confirmed containing the new `DisagreementTable` markup via direct container inspection; all 5 containers healthy throughout, zero restarts, zero errors; **grand total 601/601 unit tests passing across all 4 units** [52 Database + 268 Ingestion Worker + 191 API Service + 90 Frontend], zero regressions)

**Matching Precision Refinement: COMPLETE** — on branch `feature/recurring-payments-budget-alerts`, not yet merged to `main`.

---

## Post-Completion Change: Configurable Application Settings

Tracked separately (base project status unchanged: COMPLETE; all prior post-completion changes above also COMPLETE). Continuing on git branch `feature/recurring-payments-budget-alerts`. Explicitly deferred out of Matching Precision Refinement's Build and Test stage (see that section above and `matching-precision-refinement-build-and-test-summary.md`) due to its distinct security/architecture surface: which settings are safe to expose vs. sensitive, a real config-write + container-restart mechanism (both `Settings` classes are env-var-backed pydantic objects read once at process start), and a likely Docker-socket access decision.

- [ ] Requirements Analysis — In Progress (2026-08-16; `aidlc-docs/inception/requirements/configurable-app-settings-questions.md` created with 8 questions — settings scope, restart-trigger architecture [Docker socket placement], value-persistence/reload mechanism, worker mid-poll-cycle restart timing, Settings page placement, validation strictness, change-history/audit-trail, and auth requirements for saving a setting. Discovered while reading code: both `config.py` files have no `env_file` configured [process-env-only, `.env` is compose-only]; `docker-compose.yml`'s `ingestion-worker.environment:` block is missing mappings for many already-existing settings [gap must be closed regardless of other answers]; no Docker-socket/restart code exists anywhere today. Round 1 answered 2026-08-16: Q1=C [full Expose + Advanced tables], Q2=C [no automation, manual restart banner+command], Q3=A [override file + plain `docker restart`], Q4=B [wait for poll cycle to finish], Q5=A [section on existing SettingsPage.tsx], Q6=A [strict validation], Q7=A [change history persisted+visible], Q8=B [extra confirmation step]. One contradiction detected [Q4 assumes automated restart, Q2 rules automation out] -- `configurable-app-settings-clarification-questions.md` created, 1 question, awaiting answer.
- Feature branch `feature/configurable-app-settings` created 2026-08-16 (from this worktree's HEAD, same commit as `feature/recurring-payments-budget-alerts`).
- [x] Requirements Analysis — Complete & Approved (2026-08-16; `aidlc-docs/inception/requirements/configurable-app-settings-requirements.md`; 10 FRs, 6 NFRs; 35 settings in scope [28 standard + 7 advanced], manual restart only [no Docker socket/automation], override file + `env_file` mechanism [not root `.env`], persisted change history, extra UI confirmation step)

- [x] User Stories — Complete & Approved (2026-08-16; `configurable-app-settings-user-stories-assessment.md` [Execute=Yes]; `configurable-app-settings-story-generation-plan.md` approved [all conventions inherited, one flagged naming assumption]; `configurable-app-settings-stories.md` generated — Epic 10, 4 stories [US-10.1..10.4] covering FR-CAS-1..10/NFR-CAS-1..6; `personas.md` unchanged). **Blanket approval granted for remaining stage-completion gates on this feature** — proceed without stopping except for genuine open questions/ambiguities.

- [x] Workflow Planning — Complete & Approved (2026-08-16; `configurable-app-settings-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP, per-unit NFR Requirements/NFR Design SKIP, Functional Design EXECUTE per unit, Infrastructure Design EXECUTE [Ingestion Worker Service unit, covers both services' docker-compose blocks], Code Generation + Build and Test ALWAYS; sequence Database → {Ingestion Worker Service, API Service} → Frontend SPA; Risk: Medium-High)

- [x] Application Design — Complete & Approved (2026-08-16; blanket approval; `configurable-app-settings-application-design-plan.md`; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; Configuration Component extended [no new component]; new `setting_changes` entity; busy/idle reuses existing `IngestionRun`/`RecategorizationJob` DB state, no new table; new shared file volume for the settings-override channel [forced by a startup-ordering constraint, not a preference]; 2 ASCII diagrams width-verified programmatically)
- [x] Units Generation — Skipped (2026-08-16; existing 4 units, no new one, per approved execution plan)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Build order: Database → {Ingestion Worker Service, API Service} → Frontend SPA
- [ ] Construction — pending
  - [x] Database — Functional Design: Complete & Approved (2026-08-16; blanket approval; `domain-entities.md` +`SettingChange` entity, `business-rules.md` BR-28..29, `business-logic-model.md` +Non-Lifecycle Note)
  - [x] Database — Code Generation: Complete & Approved (2026-08-16; blanket approval; `models.py` +`SettingOwningService`/`SettingChange`, migration `0013_setting_changes.py`, `test_models.py` +`TestSettingChange` 5 tests, 57/57 unit tests passing, migration live-verified against real Postgres incl. upgrade/downgrade/idempotent-reupgrade, `/health` green throughout, 6142 real transactions untouched)

**UNIT: DATABASE — COMPLETE (for this feature)**
  - [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-16; blanket approval; `business-rules.md` WR-33 -- override-file-as-highest-precedence-source via `settings_customise_sources()`, empirically verified against pydantic-settings' real behavior rather than assumed; `extra='ignore'` also required, empirically verified)
  - [x] Ingestion Worker Service — Infrastructure Design: Complete & Approved (2026-08-16; blanket approval; new named `settings-override` Docker volume shared by both services; closed the pre-existing docker-compose env-mapping gap for all 35 settings)
  - [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-16; blanket approval; `config.py` +`SETTINGS_OVERRIDE_FILE`/`extra='ignore'`/`settings_customise_sources()`, new `test_config.py` 4 tests, 272/272 unit tests passing [up from 268]; `docker-compose.yml` +`settings-override` volume + closed env-mapping gap for all 35 settings; `.env.example` +23 previously-undocumented vars; `docker compose config`/`build ingestion-worker` verified clean)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature)**
  - [x] API Service — Functional Design: Complete & Approved (2026-08-16; blanket approval; `business-rules.md` AR-28..33 -- full 35-setting allow-list table with type/range, 2 cross-field constraints, restart command, busy/idle advisory semantics, shared config-loading mechanism, write-ordering; `domain-entities.md` +7 DTOs)
  - [x] API Service — Code Generation: Complete & Approved (2026-08-16; blanket approval; new `app_settings/` package [catalog.py, validation.py, service.py, repository.py, router.py, schemas.py], 5 endpoints; `config.py` +AR-32 mechanism; `errors.py` +2 exceptions; setting count corrected 35->40 [real discrepancy found building the catalog against actual config.py fields, documented as a Post-Approval Change]; `gemini_model` shared-setting dual-restart-target design found+fixed; 236/236 unit tests passing [up from 191]; OpenAPI 44 paths [up from 40]; `docker compose build api-service` verified clean)

**UNIT: API SERVICE — COMPLETE (for this feature)**
  - [x] Frontend SPA — Functional Design: Complete & Approved (2026-08-16; blanket approval; `frontend-components.md` +Application Settings section addendum -- ApplicationSettingsSection, SettingRow, confirmation-dialog save flow, RestartGuidanceBanner with busy/idle polling, collapsed-by-default SettingHistoryList)
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-16; blanket approval; `types.ts` +6 DTOs, new `api/settings.ts`; `SettingsPage.tsx` +ApplicationSettingsSection/SettingRow/SettingConfirmDialog/RestartGuidanceList/SettingHistoryList; `SettingsPage.test.tsx` +5 tests [default mock added so pre-existing tests unaffected]; 95/95 frontend tests passing [up from 90]; clean `tsc -b`+`vitest run`+`docker compose build frontend` [ran inside a node:20-alpine container, no local Node])

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**

**ALL 4 UNITS COMPLETE (for this feature) — proceeding to Build and Test**
