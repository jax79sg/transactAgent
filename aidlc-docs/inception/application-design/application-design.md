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
2. **API Service** — Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration, **Recategorization Review** *(added 2026-08-02, extended 2026-08-16 for disagreement review)*, **Backup Status** *(added 2026-08-08)*, **Recurring Payments** *(added 2026-08-08, Epic 8)*
3. **Ingestion Worker Service** — Ingestion Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine *(extended 2026-08-16 — always-on batch LLM classification, disagreement detection, price-bucket + boosted embedding matching)*, Currency Conversion, **Backup Manager** *(added 2026-08-08)*, **Recurring Payment Manager** *(added 2026-08-08, Epic 8; extended 2026-08-16)*, **Vector Store Client** *(added 2026-08-11, Epic 9)*, **Embedding Manager** *(added 2026-08-11, Epic 9)*
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
