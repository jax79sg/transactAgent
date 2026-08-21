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

## CONSTRUCTION PHASE (Configurable Application Settings): COMPLETE

- [x] Build and Test — Complete (2026-08-16; `aidlc-docs/construction/build-and-test/configurable-app-settings-build-and-test-summary.md`; merged into `feature/recurring-payments-budget-alerts` in the main checkout [/Users/jax/projects/transactAgent] and redeployed via `docker compose build`/`up -d --build` against the real live stack [6142 real transactions]; migration 0013 auto-applied and verified; core override mechanism live-verified end-to-end [real PUT -> real `docker restart transactagent-worker` -> confirmed new value in effect via container logs]; security boundary, validation, 40-setting count, history, and idle-state restart guidance all live-verified via real HTTP requests; deployed frontend bundle confirmed containing the new markup; full browser click-through blocked by a browser-automation-tool token-persistence quirk [not a product issue, reported honestly]; cleanup done [test setting reverted, worker restarted again, history rows kept per BR-28's append-only design, no placeholder user-data ever inserted]; 660/660 unit tests passing across all 4 units [57 Database + 272 Ingestion Worker + 236 API Service + 95 Frontend], zero regressions)

**Configurable Application Settings: COMPLETE** — merged into `feature/recurring-payments-budget-alerts` in the main checkout, not yet merged to `main`.

## Post-Delivery Correction (2026-08-16)

- [x] Fixed 3 real defects found from direct user verification: (1) never-overridden settings displayed a stale hardcoded default instead of the real deployed `.env` value [root cause: `api-service` had no visibility into Ingestion-Worker-owned env vars; fixed via a display-only Settings mirror fed the same docker-compose env vars]; (2) no per-setting description/category despite `.env.example` being well-organized [fixed: 7 categories + real descriptions sourced from `.env.example`/`config.py`, added to `SettingDTO`]; (3) `ai_assistant_max_transactions` was in-scope per the original Requirements but never implemented [added; true count 41, not 40]. Live-reverified against the real deployment (`openrouter_model`/`embedding_base_url` now correctly show real `.env` values). 663/663 unit tests passing [up from 660]. Full write-up: `configurable-app-settings-build-and-test-summary.md`'s "Post-Summary Correction" section.

---

## Post-Completion Change: Categorization Model Fine-Tuning

Tracked separately (base project status unchanged: COMPLETE; all prior post-completion changes above also COMPLETE).

- [x] Requirements Analysis — Complete & Approved (2026-08-17; `aidlc-docs/inception/requirements/categorization-model-finetuning-requirements.md`; 10 FRs, 6 NFRs). Real hardware mismatch found and resolved during this phase: the categorization LLM (`gemma-4-26b-a4b-it-4bit`) is served via oMLX on the same Mac, which has no CUDA GPU, so the originally-named Unsloth library (CUDA-only) cannot run there — resolved via user-proposed, independently-verified substitution with `mlx-tune` (MLX-native, Apple-Silicon, explicitly supports this exact model). Ground-truth dataset selection required investigating the real data model (`recategorization_proposals`/`categorization_disagreements` audit trails) since "human-approved similarity" isn't a distinct field — resolved to a real, queried, 1247-row (manual + human-approved-similarity) dataset. `categorization-model-finetuning-questions.md` (10 questions) + `categorization-model-finetuning-clarification-questions.md` (2 clarifications, both resolved) both fully answered.
- [x] User Stories — Skipped (2026-08-17; developer/ML tooling feature, no new user-facing functionality or personas; recommendation accepted implicitly on approval)
- [x] Workflow Planning — Complete & Approved (2026-08-17; `aidlc-docs/inception/plans/categorization-model-finetuning-execution-plan.md`; Application Design EXECUTE, Units Generation EXECUTE [new Unit 5: Model Training]; per-unit: Ingestion Worker Service [Functional Design + Code Generation only, NFR/Infra SKIP -- existing tech stack], Model Training [Functional Design + NFR Requirements + NFR Design + Infrastructure Design + Code Generation, all EXECUTE -- brand-new tech stack + a real infra decision: Postgres currently has no host port published]; sequence Ingestion Worker Service -> Model Training; Risk: Medium)
- [x] Application Design — Complete & Approved (2026-08-17; `categorization-model-finetuning-application-design-plan.md`; no blocking design questions -- approved requirements already resolved every open point; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new Model Training unit -- Dataset Curator + Fine-Tuning Trainer components; Categorization Engine extended for FR-CFT-9; first purely read-only Shared-DB consumer, width-verified ASCII diagram added). **Blanket approval granted for remaining stage-completion gates on this feature** — proceed without stopping except for genuine open questions/ambiguities.
- [x] Units Generation — Complete (2026-08-17; blanket approval; added **Unit 5: Model Training** to `unit-of-work.md`/`unit-of-work-dependency.md`/`unit-of-work-story-map.md` -- own directory `model-training/`, no docker-compose entry, first read-only unit dependency in the project)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Build order: Ingestion Worker Service (Unit 3, scoped change) → Model Training (Unit 5, new)
- [ ] Construction — pending
  - [x] Ingestion Worker Service — Functional Design: Complete (2026-08-17; blanket approval; `business-rules.md` WR-34, `business-logic-model.md` Categorization Engine addendum)
  - [x] Ingestion Worker Service — Code Generation: Complete (2026-08-17; blanket approval; real discovery during implementation corrected the Functional Design's assumption -- `converted_amount_sgd` wasn't actually available at the original `classifyBatch` call site, since currency conversion ran later in the pipeline; fixed by reordering conversion to run upfront per transaction, reused rather than recomputed at persist time; `classify_batch`/`classify_batch_prompt`/`classify`/`classify_description`/`classify_descriptions_batch` all gain an amount parameter; `_format_amount_sgd` renders unavailable conversion as "unknown"; 276/276 unit tests passing [up from 272]; `docker compose build ingestion-worker` verified clean)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this feature)**
  - [x] Model Training — Functional Design: Complete (2026-08-17; blanket approval; `domain-entities.md`, `business-rules.md` MTR-1..9, `business-logic-model.md`; real gap found and resolved -- MTR-7, no on-demand-classification endpoint exists anywhere in this codebase, resolved via an independent oMLX HTTP call rather than a new endpoint)
  - [x] Model Training — NFR Requirements: Complete (2026-08-17; blanket approval; `nfr-requirements.md`, `tech-stack-decisions.md`; platform constraint identified -- mlx-tune needs Metal, no Docker path exists on this Mac at all)
  - [x] Model Training — NFR Design: Complete (2026-08-17; blanket approval; `nfr-design-patterns.md`, `logical-components.md`)
  - [x] Model Training — Infrastructure Design: Complete (2026-08-17; blanket approval; `infrastructure-design.md`, `deployment-architecture.md`; resolved the Postgres-no-host-port gap via a loopback-only `127.0.0.1:5433` mapping, applied to `docker-compose.yml` and live-verified)
  - [x] Model Training — Code Generation: Complete (2026-08-17; blanket approval; full `model-training/` unit created, 29/29 tests passing; real correction found via installed-package signature verification -- Gemma 4 requires mlx-tune's VLM API path (`FastVisionModel`/`VLMSFTTrainer`), not the plain-text path the README quick start and this feature's earlier design docs assumed; real live curation run against production DB produced 1,245 real training examples)

**UNIT: MODEL TRAINING — COMPLETE (code + tests; live fine-tuning smoke test deferred, see build-and-test-summary)**

**ALL 2 UNITS COMPLETE (for this feature) — proceeding to Build and Test**

## CONSTRUCTION PHASE (Categorization Model Fine-Tuning): Code Generation complete for both units

- [x] Build and Test — Partially Complete (2026-08-17; `aidlc-docs/construction/build-and-test/categorization-model-finetuning-build-and-test-summary.md`; 276/276 Ingestion Worker + 29/29 Model Training unit tests passing; real live curation run against production DB verified; real API-signature verification against installed mlx-tune/clearml packages; Infrastructure change [Postgres port] live-verified. **Deferred**: full live fine-tuning smoke test [needs the user's oMLX server running, not currently up] and Ingestion Worker Service's live container redeploy [a real production categorization-prompt behavior change, held for explicit user go-ahead rather than silently deployed])

---

## Post-Completion Change: Model Training — ClearML/PyJWT Security Dependency Upgrade

Tracked separately (base project + feature status above unchanged). Request type: Upgrade (security remediation), single existing unit, no user-facing/functional/API/data-model impact -- Requirements Analysis executed at Minimal depth (request was exceptionally clear and complete, clarifying-questions gate skipped per `requirements-analysis.md` Step 6); User Stories, Application Design, Units Generation, and all per-unit design stages (Functional/NFR Requirements/NFR Design/Infrastructure Design) SKIPPED as simple/isolated maintenance with clear, low-risk, easily-rollback-able scope.

- [x] Requirements Analysis — Complete (2026-08-18; Minimal depth; pip-audit flagged `clearml` 1.18.0 [PYSEC-2026-1255, fixed 2.0.2+] and transitive `pyjwt` 2.9.0 [6 CVEs, fixed 2.12.0-2.13.0] in `model-training/pyproject.toml`)
- [x] Workflow Planning — Complete (2026-08-18; Code Generation + Build and Test only; all other INCEPTION/per-unit CONSTRUCTION stages skipped per above)
- [x] Code Generation — Complete (2026-08-18; researched clearml's GitHub release notes for every 2.x tag [v2.0.0 through v2.1.11] — no breaking changes found to `Task.init`/`Task.connect`/`Task.get_logger`/`Logger.report_table`/`Logger.report_scalar`/`Task.upload_artifact`/`Task.close`, the exact calls `train.py` makes; v2.0.0 explicitly updated its `pyjwt` constraint. Bumped `clearml>=1.16,<2.0` → `clearml>=2.0,<3.0` in `model-training/pyproject.toml`. `uv sync` alone resolved clearml to 2.1.11 but kept `pyjwt` pinned at the still-vulnerable 2.9.0 [clearml's own constraint is only `>=2.4.0,<3.0.0`, and uv's default sync doesn't gratuitously bump an already-satisfying transitive pin] — required a follow-up `uv lock --upgrade-package pyjwt` to actually reach 2.13.0. Re-verified all 7 calls' signatures via `inspect.signature()` against the real installed clearml 2.1.11 (not docs) — every kwarg `train.py` uses is present unchanged; no code changes needed to `train.py`.)
- [x] Build and Test — Complete (2026-08-18; 29/29 unit tests passing before and after the upgrade; `pip-audit` before: 14 known vulnerabilities across clearml+pyjwt [+1 unrelated pytest finding]; after: 0 for clearml/pyjwt, only the pre-existing unrelated pytest finding remains. Only `model-training/pyproject.toml` and `model-training/uv.lock` changed.)

**STATUS: COMPLETE** (clearml 1.18.0→2.1.11, pyjwt 2.9.0→2.13.0, no train.py code changes, 29/29 tests passing, pip-audit clean for clearml/pyjwt)

---

## Post-Completion Change: Background Process Visibility

Tracked separately (base project + all prior post-completion changes above unchanged/COMPLETE).

- [x] Requirements Analysis — Complete & Approved (2026-08-18; `aidlc-docs/inception/requirements/background-process-visibility-requirements.md`; 7 FRs, 5 NFRs; 1 round of 5 questions, all answered — scope limited to the 2 job types [ingestion runs, recategorization jobs] with real in-progress DB tracking today [Q1=C, phased — backup/detection-scan/embedding-batch deferred, would need a schema change]; both nav bar indicator + detail panel [Q2=C]; shows which job is running plus recent-completions history [Q3=C]; fast few-second polling [Q4=A]; visually distinct from the existing amber-pill count badges, e.g. spinner/pulsing [Q5=B]. One scope note resolved without a follow-up question: Q3's history option was framed around the 3 deferred job types, but both in-scope types already have real `completed_at` timestamps, so history is achievable for them within this phase.)

- [x] User Stories — Complete & Approved (2026-08-18; `background-process-visibility-user-stories-assessment.md` [Execute=Yes]; `background-process-visibility-story-generation-plan.md` [no open questions -- fully determined by established precedent]; `background-process-visibility-stories.md` generated -- Epic 11, 3 stories [US-11.1..11.3] covering FR-BPV-1..7/NFR-BPV-1..5; `personas.md` unchanged). **Blanket approval in effect for remaining stage-completion gates on this feature.**

- [x] Workflow Planning — Complete & Approved (2026-08-18; `background-process-visibility-execution-plan.md`; Application Design EXECUTE, Units Generation SKIP; per-unit Functional Design EXECUTE for API Service + Frontend SPA only [Database/Ingestion Worker Service need no changes], NFR Requirements/NFR Design/Infrastructure Design SKIP across the board, Code Generation + Build and Test ALWAYS; sequence API Service → Frontend SPA; Risk: Low)

- [x] Application Design — Complete & Approved (2026-08-18; blanket approval; `background-process-visibility-application-design-plan.md`; updated `components.md`, `component-methods.md`, `services.md`, `component-dependency.md`, `application-design.md` in place with dated addenda; new Background Activity Component [API Service] -- `getActivitySummary()` single endpoint, read-only against `ingestion_runs`/`recategorization_jobs`; Frontend SPA addendum for the nav indicator + detail panel; no Database/Ingestion Worker Service changes)
- [x] Units Generation — Skipped (2026-08-18; reuses all 4 existing units, per approved execution plan)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Build order: API Service → Frontend SPA (Database, Ingestion Worker Service unaffected)
- [ ] Construction — pending
  - [x] API Service — Functional Design: Complete (2026-08-18; blanket approval; `business-rules.md` AR-35..37, `domain-entities.md` +`ActivitySummaryDTO`/`CurrentActivityDTO`/`RecentActivityEntryDTO`, `business-logic-model.md` +Background Activity Component section)
  - [x] Frontend SPA — Functional Design: Complete (2026-08-18; blanket approval; `frontend-components.md` +NavBar ActivityIndicator/ActivityPanel addendum -- pulsing indicator + click-to-open popover, no new route)
  - [x] API Service — Code Generation: Complete (2026-08-18; blanket approval; new `background_activity/` package [schemas.py, repository.py, service.py, router.py], 1 endpoint `GET /background-activity/summary`; `main.py` router registration; 14 new tests, 253/253 unit tests passing [up from 239]; `docker compose build api-service` verified clean)

**UNIT: API SERVICE — COMPLETE (for this feature)**
  - [x] Frontend SPA — Code Generation: Complete (2026-08-18; blanket approval; found+fixed a real Functional Design gap during implementation -- idle-state indicator corrected from "renders nothing" to "always clickable, low visual weight", since history [US-11.3] must stay reachable regardless of running state; `types.ts` +4 DTOs, new `api/backgroundActivity.ts`, `NavBar.tsx` +`ActivityIndicator` [3s poll, click-to-open panel]; `NavBar.test.tsx` +4 new tests; 99/99 frontend tests passing [up from 95]; clean `eslint`+`tsc -b`+`vite build`+`docker compose build frontend`)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**
**ALL 2 AFFECTED UNITS COMPLETE — proceeding to Build and Test**

## CONSTRUCTION PHASE (Background Process Visibility): COMPLETE

- [x] Build and Test — Complete (2026-08-18; `background-process-visibility-build-and-test-summary.md`; both affected services rebuilt + redeployed against the real live stack, both healthy; live-verified `GET /background-activity/summary` with a minted JWT -- caught a genuinely real running recategorization_job at check time; real browser-based visual verification confirmed the pulsing indicator + click-to-open panel render correctly against live data; deployed frontend bundle confirmed containing new markup; 18 new tests, zero regressions [253/253 API Service, 99/99 Frontend]; no migrations, no schema changes)

**Background Process Visibility: COMPLETE** — build and test approved 2026-08-18; both changed services (API Service, Frontend SPA) live and healthy on `main`'s working tree, not yet committed to git.

---

## Post-Completion Change: Recategorization Scope Narrowing

Tracked separately (base project + all prior post-completion changes above unchanged/COMPLETE).

- [x] Requirements Analysis — Complete & Approved (2026-08-19; `recategorization-scope-narrowing-requirements.md`; 4 FRs, 3 NFRs; 1 round of 4 questions, all answered -- user rejected the originally-proposed "Others" category bucket entirely [Q1=D/Q2=C], simplifying scope to UNSURE-only, a straight reversion of WR-9's original broadening; existing pending proposals from the old scope left untouched [Q3=A]; scope confirmed limited to the retroactive re-scan only, not ingestion-time categorization [Q4=A])
- [x] User Stories — Skipped (2026-08-19; pure backend accuracy fix narrowing an existing candidate-scan's internal logic, no new user-facing workflow, no UI change -- matches precedent of prior backend-only algorithm changes)
- [x] Workflow Planning — Complete & Approved (2026-08-19; `recategorization-scope-narrowing-execution-plan.md`; Application Design SKIP [no new component/method signature], Units Generation SKIP; single unit affected -- Ingestion Worker Service only; Functional Design EXECUTE, NFR Requirements/NFR Design/Infrastructure Design SKIP, Code Generation + Build and Test ALWAYS; Risk: Low)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
- [x] Ingestion Worker Service — Functional Design: Complete & Approved (2026-08-19; `business-rules.md` WR-9 revised in place -- already-categorized bucket removed entirely, reverting to WR-5's original UNSURE-only scope; WR-10 marked moot but kept, since historical CATEGORIZED-bucket proposals still exist and are left unreviewed)
- [x] Ingestion Worker Service — Code Generation: Complete & Approved (2026-08-19; `categorization/service.py`'s Bucket B loop removed from `recategorize_unsure_from_precedent`; `categorization/repository.py`'s now-fully-unused `find_categorized_transactions_excluding` deleted; tests updated -- 1 replaced [asserts no proposal at all, not just non-auto-applied], 2 removed [exercised protections only reachable inside the deleted query]; 274/274 unit tests passing [down from 276, net of removals/additions]; `docker compose build ingestion-worker` verified clean)

**UNIT: INGESTION WORKER SERVICE — COMPLETE (for this change)**

## CONSTRUCTION PHASE (Recategorization Scope Narrowing): COMPLETE

- [x] Build and Test — Complete (2026-08-19; `recategorization-scope-narrowing-build-and-test-summary.md`; redeployed against the real live stack, healthy; live-verified the actual deployed function against placeholder rows inside a rolled-back DB transaction [zero data committed, no real correction triggered] -- confirmed an exact-match already-categorized candidate now gets zero proposal at all [previously always PENDING even at score 100], and the surviving UNSURE bucket's auto-apply behavior is genuinely unchanged; existing historical pending proposals from the old scope confirmed untouched)

**Recategorization Scope Narrowing: COMPLETE** — build and test approved 2026-08-19; ingestion-worker live and healthy on `main`'s working tree, committed 2026-08-21 (`df19a24`).

---

## Post-Completion Change: Dark Mode (GitHub Issue #1)

Tracked separately (base project + all prior post-completion changes above unchanged/COMPLETE). Source: GitHub issue #1 ("Need a dark mode"). Frontend SPA only — no Database/Ingestion Worker Service/API Service changes.

- [x] Requirements Analysis — Complete & Approved (2026-08-21; `dark-mode-requirements.md`; 8 FRs, 6 NFRs; 1 round of 6 questions, all answered, no contradictions — default to OS preference with manual NavBar-toggle override [Q1=C/Q2=A], `localStorage` persistence [Q3=A], entire app including Chart.js charts in scope [Q4=A], polished/accessible design pass rather than a mechanical color swap [Q5=B], no palette constraints [Q6=A])
- [x] User Stories — Complete & Approved (2026-08-21; `dark-mode-user-stories-assessment.md` [Execute=Yes]; `dark-mode-story-generation-plan.md` approved [no open questions -- fully determined by established precedent]; `dark-mode-stories.md` generated -- Epic 12, 4 stories [US-12.1..12.4] covering FR-DM-1..8/NFR-DM-1..6; `personas.md` unchanged)
- [x] Workflow Planning — Complete & Approved (2026-08-21; `dark-mode-execution-plan.md`; Application Design SKIP [no new component/service], Units Generation SKIP [existing Frontend SPA unit reused], per-unit Functional Design/NFR Requirements/NFR Design/Infrastructure Design all SKIP [pure presentation change, no business logic/tech-stack/infra change], Code Generation + Build and Test ALWAYS; single unit affected -- Frontend SPA only; Risk: Low-Medium)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, per-unit loop)
Frontend SPA only — Database, Ingestion Worker Service, API Service unaffected
- [ ] Construction — pending
  - [x] Frontend SPA — Code Generation: Complete & Approved (2026-08-21; `frontend-dark-mode-code-generation-plan.md`, all 11 steps; new `ThemeContext.tsx`/`chartTheme.ts`/`ThemeContext.test.tsx`; `tailwind.config.js`/`index.html`/`main.tsx`/`NavBar.tsx`/`ProtectedLayout.tsx`/`ErrorBoundary.tsx`/all 7 pages/`chartColors.ts` modified; 110/110 unit tests passing [up from 99]; `tsc -b`+`eslint`+`vite build` all clean; live-verified LoginPage in both modes via a temporary dev-server container against the real running api-service; authenticated-page click-through deferred -- no real credentials used against live production data, noted honestly per `dark-mode-summary.md`)

**UNIT: FRONTEND SPA — COMPLETE (for this feature)**
**ALL UNITS COMPLETE (for this feature — only the Frontend SPA unit was affected) — proceeding to Build and Test**

## CONSTRUCTION PHASE (Dark Mode): COMPLETE

- [x] Build and Test — Complete (2026-08-21; `dark-mode-build-and-test-summary.md`; `docker compose build/up frontend` rebuilt and redeployed twice against the real live stack [second pass on explicit user retry request, identical cached image, confirmed healthy again]; deployed bundle confirmed via `curl` to contain the FOUC script and toggle markup; live browser verification of LoginPage in both color-scheme states against the real deployed container on `:8787`; 110/110 unit tests passing, `tsc -b`/`eslint`/`vite build` all clean; authenticated-page click-through deliberately not attempted -- no real credentials available against live production data)

**Dark Mode (Epic 12): COMPLETE** — committed `c0f3af8` directly to `main` and pushed to `origin/main` per explicit user instruction ("commit, merge and push"). GitHub issue #1 closed.

## FEATURE STATUS: COMPLETE — Dark Mode (Epic 12, GitHub Issue #1)

---

## Post-Completion Change: Kubernetes Deployment Support (GitHub Issue #2)

Tracked separately (base project + all prior post-completion changes above unchanged/COMPLETE). Source: GitHub issue #2 ("Support for deployment into K8S" — "Make this a scalable deployment on K8S please."). Working on git branch `2-k8s-deployment` (created off `main` before any code changes, per the new `.claude/skills/git-issue-workflow/SKILL.md` this project adopted after user feedback on the Dark Mode feature's git handling).

- [x] Requirements Analysis — Complete & Approved (2026-08-21; `k8s-deployment-requirements.md`; 13 FRs, 6 NFRs, Complex/Comprehensive depth; 1 round of 9 questions + 1 round of 4 clarifications, all answered, no unresolved contradictions — Helm chart deploying all 5 services, provider-agnostic manifests targeting the user's OrbStack cluster, HPA on api-service/frontend only [ingestion-worker/database/vector-db hard-constrained to 1 replica -- ingestion-worker's poll loop isn't concurrency-safe], secrets via External Secrets Operator + persistent-mode HashiCorp Vault [both cluster-shared prerequisites outside the chart], secret population via a one-time helper script reading `.env`, Ingress via OrbStack's automatic `*.orb.local` HTTPS, docker-compose kept for local dev, model-training/oMLX unchanged/out of scope, nothing installed live on the real cluster this session per explicit user instruction)

- [x] User Stories — Skipped (2026-08-21; pure infrastructure/deployment change, no new user-facing functionality or workflow -- matches Categorization Model Fine-Tuning / ClearML-PyJWT Upgrade precedent)
- [x] Workflow Planning — Complete & Approved (2026-08-21; `k8s-deployment-execution-plan.md`; Application Design SKIP, Units Generation SKIP; NFR Requirements + NFR Design + Infrastructure Design EXECUTE [cross-cutting, tracked under new `aidlc-docs/construction/k8s-deployment/` rather than one existing unit's folder]; Code Generation + Build and Test ALWAYS [Build and Test scope-limited to `helm lint`/`helm template` per NFR-K8S-3, no live cluster changes]; Risk: Medium-High)

## INCEPTION PHASE (this change): COMPLETE

### 🟢 CONSTRUCTION PHASE (this change, cross-cutting)
- [ ] Construction — pending
  - [x] NFR Requirements: Complete & Approved (2026-08-21; `k8s-deployment-nfr-requirements-plan.md`, 2 questions [HPA min1/max3/80%CPU; no existing Ingress controller confirmed live via read-only `kubectl` check, so ingress-nginx setup material included]; `nfr-requirements.md` + `tech-stack-decisions.md` generated -- StatefulSet for database/vector-db, Deployment for api-service/frontend/ingestion-worker [replicas hardcoded, not values-exposed], ESO+Vault [Kubernetes auth method, Raft single-node persistent mode, standard 5/3 unseal], ingress-nginx + OrbStack `*.orb.local`-style hostname, `/api` path routing resolving the frontend API-URL design note, resource requests/limits table, PVC sizing)
  - [x] NFR Design: Complete & Approved (2026-08-21; `nfr-design-patterns.md` + `logical-components.md` -- probe-driven self-healing, deliberate PDB omission, least-privilege Vault policy, NetworkPolicy hardening for database/vector-db, dedicated `transactagent` namespace; full object inventory: 2 StatefulSets, 3 Deployments, 2 HPAs, ExternalSecret/ConfigMap, Ingress, 2 NetworkPolicies)
  - [x] Infrastructure Design: Complete & Approved (2026-08-21; `infrastructure-design.md` + `deployment-architecture.md`; explicit out-of-scope list [monitoring stack, CI/CD, multi-env promotion -- none requested]; concrete chart file tree under `deploy/helm/transactagent/` + `deploy/helm/prerequisites/` + `deploy/scripts/`; `values.yaml` schema outline; 4-namespace topology diagram with traffic flow and secret flow both walked through step-by-step)
  - [x] Code Generation: Complete & Approved (2026-08-21; `k8s-deployment-code-generation-plan.md`, all 13 steps; full Helm chart [18 templates] + prerequisites + populate-vault-secrets.sh; found+fixed a real bug during generation [Ingress /api path needed rewrite-target to strip the prefix, or every API call would 404]; used StatefulSet volumeClaimTemplates instead of standalone PVCs [design-sketch deviation, simpler/more idiomatic]; `helm lint` clean, `helm template` renders 18 valid docs, `kubectl apply --dry-run=client` against the real OrbStack cluster validates 16/18 resources clean [2 ExternalSecret/SecretStore CRD resources correctly fail, ESO not installed yet -- expected]; replica-safety constraint structurally re-verified via a nonsense override attempt)

**CONSTRUCTION: COMPLETE (for this feature, cross-cutting -- not tied to one unit)**

- [x] Build and Test — Complete (2026-08-21; `k8s-deployment-build-and-test-summary.md`; `helm lint --strict` clean, `shellcheck` clean on the population script, 16/18 resources validated via real-cluster `kubectl apply --dry-run=client` [zero mutation], 2 correctly-expected ExternalSecret/SecretStore CRD failures documented as expected not defects; replica-safety + values-propagation re-verified structurally; explicit checklist documented for what real end-to-end verification would still require, owned by the user per their choice not to install anything live this session)

## CONSTRUCTION PHASE (K8s Deployment): COMPLETE

## Post-Build-and-Test: Live End-to-End Verification (user-initiated, 2026-08-21)

Superseding NFR-K8S-3's original "no live changes this session" scope, per explicit user request to actually test the deployment. Installed all 3 prerequisites (ingress-nginx, Vault persistent/Raft, ESO) live on the user's real OrbStack cluster, initialized/unsealed Vault, populated real secrets, `helm install`ed the app chart. Found and fixed 4 real bugs live:
1. `image.registry` empty-string produced a broken image reference — fixed (`83666a6`)
2. ExternalSecret/SecretStore used a non-served API version + an invalid cross-namespace ServiceAccount ref for a namespaced SecretStore — fixed to `v1` + `ClusterSecretStore` (`dd2fc42`)
3. **Migration `0001`/`0007` fresh-database drift** — a pre-existing, previously-flagged-never-fixed bug (unrelated to K8s) that blocked the database from bootstrapping at all from empty; root-caused, fixed, and rigorously verified (byte-for-byte schema match against real production) on a separate branch/PR — see `fix/migration-0001-fresh-db-drift`, PR #4
4. Frontend's `buildUrl()` silently dropped `apiBaseUrl`'s path component for a path-prefixed API URL (only ever triggered by this K8s Ingress's own `/api` routing design) — fixed (`09ab498`)

**Live-verified end-to-end via a real browser**: login page renders correctly over real OrbStack HTTPS at `https://transactagent.k8s.orb.local/`; a real login attempt correctly reaches `api-service` through the Ingress and returns a genuine 401 ("Invalid username or password") — full browser→Ingress→api-service→Postgres round trip proven working, not just chart-rendering validation.

Two PRs open, neither merged (per `git-issue-workflow` — functional verification is not merge approval):
- PR #3 — Kubernetes Deployment Support (`2-k8s-deployment` → `main`)
- PR #4 — Migration fresh-database drift fix (`fix/migration-0001-fresh-db-drift` → `main`), a prerequisite for PR #3's database to actually bootstrap from scratch

## FEATURE STATUS: LIVE-VERIFIED, AWAITING MERGE — Kubernetes Deployment Support (GitHub Issue #2)
