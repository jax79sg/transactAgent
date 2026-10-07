# Application Design — Bank Transaction Insights App (Consolidated)

This document consolidates `components.md`, `component-methods.md`, `services.md`, and `component-dependency.md`. See those files for full detail; this is the executive summary.

## Architecture Decisions (from application-design-plan.md)

| Decision | Choice |
|---|---|
| Architectural style | Separate services: **API Service** + **Ingestion Worker Service**, sharing one database |
| Ingestion execution model | Async background job; API Service enqueues, Worker polls/claims, both read/write a shared run/job DB table for status (no message broker needed) |
| Categorization engine | Pluggable `CategorizationStrategy` interface (Similarity Matcher, LLM Classifier) inside the Worker Service |
| Frontend/backend API style | REST (JSON over HTTP) |

## Services

1. **Frontend SPA** — the only UI surface; talks to API Service only
2. **API Service** — Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration, **Recategorization Review** *(added 2026-08-02, extended 2026-08-16 for disagreement review)*, **Backup Status** *(added 2026-08-08)*, **Recurring Payments** *(added 2026-08-08, Epic 8)*; **Duplicate Review** *(added 2026-10-03, Epic 14)*
3. **Ingestion Worker Service** — Ingestion Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine *(extended 2026-08-16 — always-on batch LLM classification, disagreement detection, price-bucket + boosted embedding matching)*, Currency Conversion, **Backup Manager** *(added 2026-08-08)*, **Recurring Payment Manager** *(added 2026-08-08, Epic 8; extended 2026-08-16)*, **Vector Store Client** *(added 2026-08-11, Epic 9)*, **Embedding Manager** *(added 2026-08-11, Epic 9)*; **Probable Duplicate Detector** and **Statement Removal Handler** *(added 2026-10-03, Epic 14)*
4. **Shared Database** — the only integration point between API Service and Worker Service (data contract, not code contract)
5. **Vector DB** *(added 2026-08-11, Epic 9)* — a second, separate datastore, accessed only by the Ingestion Worker Service (never the API Service); not a new integration point between the two services
6. **oMLX** *(added 2026-08-11, Epic 9)* — a new external dependency, but a user-managed, host-native one, unlike every other external API this project calls; explicitly outside `docker-compose`

## Key Design Consequence Flagged During Design

Manual category correction (US-3.4) is handled entirely in the API Service, but the retroactive re-categorization of existing `UNSURE` transactions (FR-5.4) requires the Categorization Engine, which lives in the Worker Service. This is implemented as another async job (consistent with the ingestion-run pattern), not a direct synchronous call — keeping the two services fully decoupled. This means a manual correction's ripple effect on other `UNSURE` transactions completes shortly after the correction, not instantaneously — acceptable per the approved acceptance criteria, which do not require synchronous completion.

**Addendum (2026-08-02, Recategorization Review Panel — Epic 6)**: That same async job (FR-5.4) is now broadened to search already-categorized transactions too, and split by confidence: very-high-confidence `UNSURE` matches still auto-apply as before; everything else — lower-confidence `UNSURE` matches, and *every* match against an already-categorized transaction regardless of score — now creates a pending proposal instead of writing to `transactions`. Reviewing those proposals (approve/reject, individually or in bulk) is a **new, separate, synchronous** path in a new API Service component (Recategorization Review), analogous to `correctCategory()` itself rather than routed through the async job queue — a human clicking "approve" is a request/response action, not background work. See `recategorization-review-application-design-plan.md` for the full reasoning behind each of these calls.

**Addendum (2026-08-08, Nightly Transaction Backup — Epic 7)**: A new, third kind of background work — time-triggered rather than queue-triggered — is added to the Worker Service's `poll_once()` loop as a lowest-priority branch (checked only when no run/job was found that cycle), owned by the new **Backup Manager** component. It reuses the existing Drive Connector for all Google Drive I/O (extended with write/delete methods against a separate, dedicated backup Drive folder — distinct from the ingestion source folder, per the user's explicit single-point-of-failure concern) and writes status to a new `backup_runs` table. The API Service's new **Backup Status** component reads that table read-only, exposing it to the Frontend's new Review-page panel — holding the same "no direct service-to-service call" rule as Recategorization Review. See `nightly-backup-application-design-plan.md` for the full reasoning.

**Addendum (2026-08-08, Recurring Payments — Epic 8)**: Two new hooks, owned by the new **Recurring Payment Manager** component, with different triggers reflecting genuinely different natures of work. Matching a new transaction against the recurring-payments register is *transaction-triggered* — it's folded directly into the existing per-transaction persistence step in the Ingestion Orchestrator's pipeline (the moment a transaction is saved is exactly when matching should happen, no separate pass needed), reusing the Categorization Engine's similarity matcher rather than a new one (NFR-1). Detecting untracked recurring charges is *time-triggered* — a fourth `poll_once()` branch, extending the same pattern Backup Manager established. The API Service's new **Recurring Payments** component owns the register (CRUD, bulk import) and resolution of what the Worker proposes (approve/reject a match, dismiss/add-from a detection suggestion) — creation of matches and suggestions stays exclusively with the Worker, holding the same "no direct service-to-service call" rule as every prior review-style component. See `recurring-payments-application-design-plan.md` for the full reasoning.

**Addendum (2026-08-11, Local Embedding-Based Semantic Similarity — Epic 9)**: Two new Worker-side components — **Vector Store Client** (all interaction with the new, separate Vector DB, mirroring Drive Connector's role for Google Drive) and **Embedding Manager** (owns *when* a transaction's own embedding gets persisted — the async/batched storage-time computation, plus the one-time historical backfill, unified into a single poll-cycle mechanism that just keeps consuming a `pending` backlog). Critically, this is separate from *query-time* embedding computation: the Categorization Engine and Recurring Payment Manager each compute a transient, non-persisted embedding of whatever they're matching *right now* and query the Vector Store Client directly — this is what actually makes FR-3/FR-4's "embedding-first" promise true at match time, and it's not a new orchestration hook since it's just an internal step of methods that already exist. Both the existing fuzzy-text matcher (WR-3/WR-20) and the amount-range gate (NFR-1) are kept exactly as-is as the fallback and safety net respectively — nothing about them changes; embedding similarity is a new candidate-finding method layered in front of them, not a replacement. See `embedding-similarity-application-design-plan.md` for the full reasoning, including why this doesn't conflict with FR-6's async-computation requirement.

**Addendum (2026-08-16, Matching Precision Refinement, see `matching-precision-refinement-application-design-plan.md`)**: No new component or service, but three cross-cutting changes to how the Categorization Engine works. (1) The LLM Classifier moves from a last-resort fallback to an always-on step (FR-MPR-1): a new `classifyBatch` method fires concurrently for a whole file's transactions, called once upfront by the Ingestion Orchestrator, before the existing per-transaction loop — `categorize()` now takes the already-known classification as an input rather than computing it internally. (2) `categorize()`'s decision logic changes: agreement between similarity and LLM auto-assigns as before; only one signal being confident still auto-assigns directly (not treated as disagreement); both confident and differing is a genuine disagreement, recorded as a new **`CategorizationDisagreement`** entity (deliberately not an extension of `RecategorizationProposal` — different trigger, needs two candidate categories, not one) and surfaced on the existing Review page via the **Recategorization Review Component**, extended with pick-one-or-reject actions rather than a new API Service component. (3) Embedded text gains a price-range bucket and candidate scoring gains a small LLM-agreement boost, applied to the Categorization Engine's own matching *and* the Recurring Payment Manager's (reusing the same Epic 9 embedding infrastructure, price bucket and boost logic are the only things that change there). Each transaction's own LLM classification is now persisted (`Transaction.llm_suggested_category_id`) so the retroactive re-scan can use it as a boost signal for transactions ingested earlier.

**Addendum (2026-10-03, Probable Duplicate Statement Detection — Epic 14, see `probable-duplicate-application-design-plan.md`)**: Two new Worker-side components and one API-side component. The **Probable Duplicate Detector** judges an extracted statement against the held ones (a pure matching rule plus database steps) and scans the stored statements for pairs; it is separate from the byte-checksum Duplicate Detection because it compares extracted transactions after extraction rather than bytes before. The **Statement Removal Handler** executes a confirmed removal, because deleting a statement must also delete its embeddings and the API Service never connects to the vector store: the API writes a removal job row, the worker deletes the database rows in one transaction and then the embeddings. The **Duplicate Review Component** shows the worker's findings and records the user's decisions, and never recomputes a proposal. Every remembered decision is keyed by content hash, so it stays valid across the Account Balance backfill, which recreates every statement with a new id. Detection ships switched off and is enabled after an accuracy evaluation on the live statements. `poll_once()` becomes seven branches: removal sits third (a user is waiting), the pair scan sixth (ahead of the embedding backlog, which would otherwise starve it).

## Story Traceability Validation (Step 10)

All 24 approved stories map to at least one component:

| Story | Component(s) |
|---|---|
| US-1.1 | Drive Connector |
| US-1.2 | Ingestion Trigger & Status, Ingestion Orchestrator |
| US-1.3 | Statement Extraction |
| US-1.4 | Duplicate Detection |
| US-1.5 | Ingestion Trigger & Status |
| US-2.1 | Categorization Engine (Similarity Matcher) |
| US-2.2 | Categorization Engine (LLM Classifier) |
| US-2.3 | Categorization Engine (fallback chain) |
| US-3.1 | Transaction Management |
| US-3.2 | Transaction Management |
| US-3.3 | Transaction Management |
| US-3.4 | Transaction Management, Categorization Engine (retro job) |
| US-3.5 | Transaction Management |
| US-3.6 | Transaction Management |
| US-3.7 | Transaction Management, Currency Conversion |
| US-4.1 | Dashboard/Insights |
| US-4.2 | Dashboard/Insights |
| US-4.3 | Dashboard/Insights |
| US-4.4 | Dashboard/Insights |
| US-4.5 | Dashboard/Insights, Transaction Management (drill-down target) |
| US-4.6 | Dashboard/Insights, Currency Conversion |
| US-5.1 | Auth |
| US-5.2 | Configuration |
| US-5.3 | (Environment-based, no runtime component — see components.md note) |

**Result (original 24 stories)**: Complete — no gaps. Every story has at least one owning component; no component exists without a story justifying it (no speculative/unused components).

### Addendum (2026-08-02): Epic 6 — Recategorization Review Panel

| Story | Component(s) |
|---|---|
| US-6.1 | Categorization Engine (broadened search) |
| US-6.2 | Categorization Engine (auto-apply path) |
| US-6.3 | Categorization Engine (always-review rule for already-categorized candidates) |
| US-6.4 | Recategorization Review, Frontend SPA (Review page) |
| US-6.5 | Recategorization Review |
| US-6.6 | Recategorization Review, Frontend SPA (nav badge) |

**Result (Epic 6)**: Complete — no gaps, no new speculative components. All 6 stories map to either the extended Categorization Engine or the new Recategorization Review component.

### Addendum (2026-08-08): Epic 7 — Nightly Transaction Backup

| Story | Component(s) |
|---|---|
| US-7.1 | Backup Manager, Drive Connector (extended) |
| US-7.2 | Backup Manager |
| US-7.3 | Backup Manager |
| US-7.4 | Backup Manager (status recording), Backup Status, Frontend SPA (Review page panel) |

**Result (Epic 7)**: Complete — no gaps, no new speculative components. All 4 stories map to either the extended Drive Connector or the new Backup Manager / Backup Status components.

### Addendum (2026-08-08): Epic 8 — Recurring Payments, Budget Alerts & Subscription Detection

| Story | Component(s) |
|---|---|
| US-8.1 | Recurring Payments |
| US-8.2 | Recurring Payments |
| US-8.3 | Recurring Payments (status data), Frontend SPA (Dashboard section) |
| US-8.4 | Recurring Payment Manager, Recurring Payments (review), Categorization Engine (similarity matcher, reused) |
| US-8.5 | Recurring Payment Manager |
| US-8.6 | Recurring Payment Manager, Recurring Payments (suggestion triage) |
| US-8.7 | Recurring Payments (status data), Frontend SPA (nav badge) |

**Result (Epic 8)**: Complete — no gaps, no new speculative components. All 7 stories map to either the extended Categorization Engine or the new Recurring Payment Manager / Recurring Payments components.

### Addendum (2026-08-11): Epic 9 — Local Embedding-Based Semantic Similarity

| Story | Component(s) |
|---|---|
| US-9.1 | Embedding Manager (writes status), Transaction Management (reads status), Frontend SPA (badge) |
| US-9.2 | Categorization Engine, Recurring Payment Manager (both extended), Vector Store Client |
| US-9.3 | Categorization Engine (amount-gate + manual-precedence carryover, unchanged logic) |
| US-9.4 | Embedding Manager (soft-fail), Categorization Engine / Recurring Payment Manager (fallback path) |
| US-9.5 | Embedding Manager (backfill, same mechanism as forward processing) |

**Result (Epic 9)**: Complete — no gaps, no new speculative components. All 5 stories map to either an extended existing component or one of the two new Ingestion Worker Service components (Vector Store Client, Embedding Manager).

### Addendum (2026-08-16): Matching Precision Refinement

No user stories this round (backend algorithm refinement — see `matching-precision-refinement-requirements.md`); traced directly to functional requirements instead.

| Requirement | Component(s) |
|---|---|
| FR-MPR-1, FR-MPR-2, FR-MPR-3 | Categorization Engine (`classifyBatch`), Ingestion Orchestrator (new upfront pipeline step) |
| FR-MPR-4 | Categorization Engine, Recurring Payment Manager (both, embedded text) |
| FR-MPR-5 | Categorization Engine, Recurring Payment Manager (configurable bucket boundaries) |
| FR-MPR-6 | Categorization Engine (`categorize()` decision logic) |
| FR-MPR-7 | Categorization Engine, Recurring Payment Manager (both, score boost) |
| FR-MPR-8 | Categorization Engine, Recurring Payment Manager (both, raised threshold) |
| FR-MPR-9 | Categorization Engine (writes `CategorizationDisagreement`) |
| FR-MPR-10, FR-MPR-11 | Recategorization Review Component (extended), Frontend SPA (Review page, extended `ProposalTable`/`ProposalRow`) |
| FR-MPR-12 | Categorization Engine, Recurring Payment Manager (scope boundary — no disagreement branch in the latter) |

**Result (Matching Precision Refinement)**: Complete — no gaps, no new speculative components. All 12 functional requirements map to either an extended existing component or the new `CategorizationDisagreement` data shape (Shared Data Store, not a component).

### Addendum (2026-08-16): Configurable Application Settings

See `configurable-app-settings-application-design-plan.md` for the full reasoning (4 Key Design Resolutions + 1 Component Boundary Note). Traced to Epic 10's stories.

| Story | Component(s) |
|---|---|
| US-10.1 | Configuration Component (extended: `listSettings`/`getSetting`/`updateSetting`), Frontend SPA (new "Application Settings" section) |
| US-10.2 | Configuration Component (classification metadata on `listSettings`), Frontend SPA ("Advanced" sub-heading) |
| US-10.3 | Configuration Component (`getRestartGuidance`, `isIngestionWorkerBusy` — Shared DB query, no new table), Frontend SPA (busy/idle indicator) |
| US-10.4 | Configuration Component (`listSettingHistory`, writes `SettingChange`), Frontend SPA (history view) |

**Result (Configurable Application Settings)**: Complete — no gaps, no new speculative components, no new Frontend component. All 4 stories map to the extended Configuration Component and the existing Frontend SPA convention. One genuinely new architectural element not attributable to any single component: the shared, file-backed override-settings channel between API Service and Ingestion Worker Service (Key Design Resolution 3) — a new kind of cross-service coordination, deliberately narrow in scope (config values only; busy/idle stays DB-based, Key Design Resolution 2) and forced by a real startup-ordering constraint, not a preference.

### Addendum (2026-08-17): Categorization Model Fine-Tuning

No user stories this round (developer/ML tooling — see `categorization-model-finetuning-requirements.md`); traced directly to functional requirements. This is this project's first genuinely new **unit** since the original 4 (Database, API Service, Ingestion Worker Service, Frontend SPA) — see `categorization-model-finetuning-execution-plan.md` for why it doesn't fit inside any existing one.

| Requirement | Component(s) |
|---|---|
| FR-CFT-1..4 | Dataset Curator Component (new, Model Training unit) |
| FR-CFT-5..8 | Fine-Tuning Trainer Component (new, Model Training unit) |
| FR-CFT-9 | Categorization Engine Component (extended — `classify`/`classifyBatch` gain an `amountSgd` parameter) |
| FR-CFT-10 | Model Training unit as a whole (two standalone CLI entry points — see `services.md`) |

**Result (Categorization Model Fine-Tuning)**: Complete — no gaps. All 10 functional requirements map to either the two new Model Training components or a scoped extension of the existing Categorization Engine. Two genuinely new architectural elements: (1) the Model Training unit itself — no docker-compose service, no persistent process, its own isolated ML dependency set (NFR-CFT-1); (2) the project's first purely **read-only** consumer of the Shared DB — every prior addendum above described a writer/reader pair between the two existing services, this is the first one-directional relationship. Two new external dependencies, both isolated to this one unit: HuggingFace Hub (base model download) and ClearML SaaS (run tracking).

### Addendum (2026-08-18): Background Process Visibility

See `background-process-visibility-application-design-plan.md`. Traced to Epic 11's stories.

| Story | Component(s) |
|---|---|
| US-11.1 | Background Activity Component (new, `getActivitySummary`), Frontend SPA (new nav bar indicator, fast poll) |
| US-11.2 | Background Activity Component (job-type identification in `current`) |
| US-11.3 | Background Activity Component (`recent` history list), Frontend SPA (detail panel) |

**Result (Background Process Visibility)**: Complete — no gaps, no new speculative components. All 3 stories map to one new, narrowly-scoped API Service component and the existing Frontend SPA convention (one component, no new component for the indicator/panel). No Database or Ingestion Worker Service changes — the two in-scope job types (ingestion runs, recategorization jobs) already write everything this feature reads. Scope deliberately excludes the other 3 job types (backup runs, detection scans, embedding batches) per FR-BPV-1 — they have no real in-progress DB status today, and adding one is out of scope for this phase.

### Addendum (2026-10-02): Epic 13 — Account Balance at a Point in Time

See `account-balance-application-design-plan.md`. Traced to Epic 13's stories and `account-balance-requirements.md`'s FRs. Two design questions were asked and answered: **Question 1 = A** (the Balance Component's FX as-of-date lookup is cache-only: nearest earlier cached rate, marked approximate, else unavailable; no new external dependency for API Service) and **Question 2 = A** (the Backfill Tool is a single command-line tool in the Ingestion Worker's image: no new endpoints, no UI).

| Story | Component(s) |
|---|---|
| US-13.1 | Statement Extraction (new optional fields), Account Resolver (new), Ingestion Orchestrator (new call), Duplicate Detection (`recordProcessed` stores account reference), Account Management (`listAccounts`) |
| US-13.2 | Account Management (new: rename, merge, correct type), Frontend SPA (account management UI) |
| US-13.3 | Account Management (new: `setAnchor`), Frontend SPA (anchor entry, "anchor required" prompt) |
| US-13.4 | Balance Component (new: `balanceFromAnchor`, `getBalances`, `lookupFxRateAsOf`), Frontend SPA (Dashboard lookup) |
| US-13.5 | Balance Component (`getBalanceSeries`), Frontend SPA (Dashboard chart) |
| US-13.6 | Statement Extraction + Duplicate Detection (closing-balance capture), Balance Component (`listDiscrepancies`), Frontend SPA (warnings) |
| US-13.7 | Backfill Tool Component (new, command-line only) |

| Requirement | Component(s) |
|---|---|
| FR-AB-1, FR-AB-2 | Shared DB (`accounts`), Account Resolver, Statement Extraction (account identifier) |
| FR-AB-3 | Account Management |
| FR-AB-4 | Statement Extraction (account type), Account Resolver, Balance Component (deposit accounts only) |
| FR-AB-5 | Statement Extraction (closing balance), Duplicate Detection `recordProcessed`, Shared DB (`bank_statements` columns) |
| FR-AB-6 | Account Management (`setAnchor`), Shared DB (anchors) |
| FR-AB-7 | Balance Component (`balanceFromAnchor`, the pure function) |
| FR-AB-8 | Balance Component (`listDiscrepancies`) |
| FR-AB-9 | Balance Component (`lookupFxRateAsOf`, cache-only per Question 1 = A) |
| FR-AB-10, FR-AB-11, FR-AB-14 | Balance Component (`getBalances`: month resolution, named exclusions, ingested-through date), Frontend SPA |
| FR-AB-12 | Balance Component (`getBalanceSeries`), Frontend SPA |
| FR-AB-13 | Frontend SPA (Dashboard) |
| FR-AB-15, FR-AB-16, FR-AB-17 | Backfill Tool Component |
| NFR-AB-1, NFR-AB-4 | Balance Component (exact decimals; pure function separated from I/O wrapper) |
| NFR-AB-2 | Backfill Tool Component (dry run, verified backup, typed confirmation) |
| NFR-AB-3 | Statement Extraction (new fields optional, existing safety nets untouched) |
| NFR-AB-5, NFR-AB-6, NFR-AB-7, NFR-AB-8 | Balance/Account Management (compute on request, existing auth on new routers), Frontend SPA (theme/responsive), Categorization Engine (unchanged) |

**Result (Epic 13)**: Complete — no gaps; every FR-AB, US-13.x, and NFR-AB lands on a named component. Three new components in two existing services (Account Resolver; Account Management and Balance) plus one new command-line entry point (Backfill Tool), no new container, no new external integration, and no new edge between `api-service` and `ingestion-worker` (both depend only on the Shared DB). Architecturally new elements: balances computed on request and never stored (so replaced anchors and merges cannot leave stale results), and the second command-line entry point in the project after Model Training.

**Consequences to carry forward** (not decided here):
1. **FR-AB-9 is refined by Question 1 = A.** The requirement said balances convert at "the FX rate for the requested date"; the cache-only design converts at the nearest earlier cached rate, marks the figure approximate when that rate's date differs, and shows the account as unavailable when none exists. `account-balance-requirements.md` carries a dated note on FR-AB-9. Practical effect: a foreign-currency savings account may show approximate or unavailable balances for dates far from any cached rate, since `fx_rate_cache` is populated only by the Ingestion Worker and only for dates of foreign-currency transactions that needed converting. SGD accounts are unaffected.
2. **Backfill backup mechanism (NFR-AB-2)** — the existing nightly backup covers only the `transactions` table as CSV in Drive; the worker image has no `pg_dump` and no host-mounted output directory. Functional Design must choose a mechanism and may reopen Infrastructure Design (the execution plan's stated trigger).
3. **Backfill vs. the worker's poll loop** — the tool must not interleave with a normal ingestion run; Functional Design decides the guard.
4. **Open items already listed in the requirements** still go to Functional Design: chart point granularity, cross-check tolerance, the account-identifier storage shape, and the rule that user-corrected account names/types survive later extractions.
5. **Scope change (2026-10-03): a statement may hold several accounts** (Ingestion Worker Functional Design clarification Q1 = B). Every component above that said "the statement's account" now means "each account section's account": Statement Extraction returns sections, the Account Resolver runs per section (collapsing duplicates), recording a statement writes one statement-account row per section (carrying the closing balance, which moves off the statement) and each transaction links to its section, the Balance Component reaches an account's transactions and closing balances through that link, Account Management refuses to merge two accounts that appear together in a statement, and the backfill's wipe set gains `statement_accounts`. No new component and no new edge between services; the dated notes under each component in `components.md`, `component-methods.md`, and `services.md` carry the detail, and the diagram in `component-dependency.md` lists the new `statement-accounts` entity. The traceability above still holds: US-13.1 gains the multi-account criteria, US-13.2 the merge refusal, US-13.6 the per-account closing balance, US-13.7 the section-count report.

### Addendum (2026-10-03): Epic 14 — Probable Duplicate Statement Detection

See `probable-duplicate-application-design-plan.md`. Traced to Epic 14's stories and `probable-duplicate-statements-requirements.md`'s FRs. No design question was asked: two rounds of requirements questions (8) and eight documented assumptions had resolved the product decisions, and the 14 technical decisions followed from the project's conventions. Approved together with the plan: detection ships switched off, and remembered records are keyed by content hash.

| Story | Component(s) |
|---|---|
| US-14.1 | Probable Duplicate Detector (pure rule: `isProbableDuplicate`, `matchTransactions`, `matchRatio`, `periodsOverlap`; `findProbableDuplicateOf`, `recordSkippedDuplicate`), Ingestion Orchestrator (check 2, before account resolution), Account Resolver (normalized bank key reused), Configuration (on/off, ratio, minimum) |
| US-14.2 | Probable Duplicate Detector (`selectSnapshot`), Shared DB (comparisons), Duplicate Review (`getComparison`), Ingestion Trigger & Status (comparison link on the run file), Frontend SPA (comparison view) |
| US-14.3 | Duplicate Review (`overrideSkippedFile`), Shared DB (remembered files, state `overridden`), Duplicate Detection (`lookupRememberedFile`), Frontend SPA (override action) |
| US-14.4 | Duplicate Detection (`lookupRememberedFile`, before extraction, always on), Statement Removal Handler (records the removed hash), Ingestion Orchestrator (check 1) |
| US-14.5 | Probable Duplicate Detector (`scanHeldStatements`, `isPairScanDueNow`, `runPairScan`, `chooseKeptCopy`), Duplicate Review (`listProbablePairs`, `getPendingPairCount`, `dismissPair`, `requestRecheck`), Shared DB (pairs, scan state), Frontend SPA (panel, badge) |
| US-14.6 | Duplicate Review (`confirmRemoval`, removal preview, status), Statement Removal Handler (`processNextRemoval`, `deleteStatementCascade`), Vector Store Client (`deleteEmbeddings`), Shared DB (removal jobs), Frontend SPA (confirmation, status) |
| US-14.7 | Backfill Tool (`checkDuplicates`, dry-run listing, `preRegisterSkips`, corrections carried, report), Probable Duplicate Detector (compute-only scan), Duplicate Detection (the pre-registered skip is honoured at check 1) |

| Requirement | Component(s) |
|---|---|
| FR-PD-1 | Ingestion Orchestrator (check 2 placed before the Account Resolver), Probable Duplicate Detector (`recordSkippedDuplicate` writes nothing else) |
| FR-PD-2 | Shared DB (new run-file outcome, comparison link), Ingestion Trigger & Status (DTO), Frontend SPA (label) |
| FR-PD-3, FR-PD-4 | Probable Duplicate Detector (`isProbableDuplicate`, small-statement gate), Configuration (ratio, minimum) |
| FR-PD-5, FR-PD-6 | Probable Duplicate Detector (`selectSnapshot`), Shared DB (comparisons), Duplicate Review (`getComparison`), Frontend SPA (comparison view) |
| FR-PD-7 | Duplicate Review (`overrideSkippedFile`), Duplicate Detection / Orchestrator (overridden hash proceeds and is exempt) |
| FR-PD-8, FR-PD-13 | Shared DB (remembered files), Duplicate Detection (`lookupRememberedFile`), Statement Removal Handler (records `confirmed_duplicate`) |
| FR-PD-9 | Probable Duplicate Detector (`scanHeldStatements`), Duplicate Review, Frontend SPA (panel, badge) |
| FR-PD-10 | Duplicate Review (`confirmRemoval`, `dismissPair`: nothing removed without explicit confirmation) |
| FR-PD-11 | Probable Duplicate Detector (`chooseKeptCopy`, computed once by the worker and stored on the pair), Duplicate Review (displays it) |
| FR-PD-12, FR-PD-14 | Statement Removal Handler, Vector Store Client (`deleteEmbeddings`), Shared DB (removal jobs), Duplicate Review (preview and status) |
| FR-PD-15, FR-PD-16, FR-PD-17 | Backfill Tool (`checkDuplicates`, `preRegisterSkips`, corrections carried across, report) |
| FR-PD-18 | Workflow ordering (this feature is built and enabled before the Account Balance backfill is run); Backfill Tool refuses to start while removal or scan work is pending |
| NFR-PD-1 | Backfill Tool (`check-duplicates` is the read-only evaluation), Configuration (detection ships off) |
| NFR-PD-2 | Duplicate Detection (check 1), Shared DB (remembered files) |
| NFR-PD-3 | Statement Removal Handler (re-verification, one transaction, embeddings after the commit), Duplicate Review (confirmation states counts and corrections lost) |
| NFR-PD-4 | Statement Removal Handler and Duplicate Review (no API-to-vector-store path; job row coordination) |
| NFR-PD-5 | Backfill Tool (report), Duplicate Review (override of a skipped file) |
| NFR-PD-6 | Duplicate Detection (exact-bytes check untouched and first), Ingestion Orchestrator (existing branches and review flows untouched) |
| NFR-PD-7 | Probable Duplicate Detector (the five pure functions are the property-based-testing targets) |
| NFR-PD-8 | Duplicate Review (existing auth on the new router), Frontend SPA (theme, responsive) |

**Result (Epic 14)**: Complete — no gaps; every FR-PD, US-14.x, and NFR-PD lands on a named component. Three new components (Probable Duplicate Detector and Statement Removal Handler in the Ingestion Worker, Duplicate Review in the API Service), five new entities and one enum value, one new vector-store operation, two new `poll_once()` branches, and extensions to the Backfill Tool, the Frontend SPA, Configuration, Duplicate Detection, the Orchestrator, and Ingestion Trigger & Status. No new container, no new external integration, and no new edge between `api-service` and `ingestion-worker` (both depend only on the Shared DB).

**Consequences to carry forward** (not decided here; each goes to the named Functional Design or later stage):
1. **Matching specifics (IW FD)**: the description-wording tolerance, the period-overlap definition, and the threshold values, calibrated with `check-duplicates` against the live statements (NFR-PD-1); how a **multi-account statement** is compared (all its transactions together, and what "same account" means when each side has several identifiers).
2. **Entity shapes (DB FD)**: columns, constraints, and state transitions for the five entities (uniqueness by content hash for remembered files, by unordered hash pair for pairs); what a removal job keeps (the removed transaction ids until their embeddings are confirmed gone); whether scan state is its own row or folded into one; the migration (0020); the run-file outcome enum value and comparison link; backup and restore coverage of the new tables.
3. **Statement label (DB/IW FD)**: `bank_statements` has no file name; the label (file name, bank, period, A-PD-3) is resolved from the run file that processed the statement (`ingestion_run_files.bank_statement_id`) and **stored inside the comparison**, so it survives the statement being changed or removed.
4. **Removal safety (IW FD)**: the re-verification at execution (target present; manual corrections not above the acknowledged count); bounded retries and parking for a removal that cannot finish, because branch 3 outranks backup and the scans; what the API shows for "embeddings pending".
5. **One list of what depends on a transaction (DB/IW/API FD)**: the removal helper, the Backfill Tool's wipe, and the API's removal preview must agree. The wipe order moves into one shared helper, and a guard test derived from the foreign-key metadata fails if a new table ever depends on `transactions` without being listed.
6. **Backfill interaction (IW FD)**: the tool refuses while a removal job or scan is pending; `run` clears the pending pairs the reingest resolves, honours dismissed pairs, pre-registers the rest, carries corrections for every probable-duplicate skip made during the reingest (pre-registered or inline), and requests a re-scan when it finishes; `restore` reverts the new tables.
7. **Scan-due conditions and settings (IW FD / API FD)**: exactly which setting changes make a scan due; the three setting names, bounds, and defaults (off, 0.80, 3) and the catalog's asserted entry count (44 today).
8. **Frontend (FE FD)**: separate versus combined nav badge, the comparison view's route or modal, and the empty and failed states.
9. **Accuracy gate (Build and Test, first)**: before detection is switched on or the Account Balance backfill is run, `check-duplicates` must show both June pairs flagged, the CIMB look-alikes not, and nothing else unreviewed (NFR-PD-1).
