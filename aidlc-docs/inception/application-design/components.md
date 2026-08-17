# Components — Bank Transaction Insights App

Architectural style: **Separate services** (Question 1 = B) — an **API Service** and an **Ingestion Worker Service**, both sharing one PostgreSQL-class database, plus a **Frontend** SPA. Components below are grouped by which deployable service owns them.

---

## Frontend

### Frontend SPA
- **Purpose**: Rich single-page web application — the only surface the Account Owner interacts with directly.
- **Responsibilities**: Login screen; ingestion trigger + live progress/run history views; transaction table with filter/group/sort/export; manual category correction UI; dashboards (category trends, cash flow, bank breakdowns) with drill-down; category whitelist settings.
- **Interfaces**: Consumes the API Service's REST API (Question 4 = A) exclusively — never talks to the Ingestion Worker or database directly.
- **Stories covered**: All 24 (as the presentation layer for every capability).
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: Adds a Review page (US-6.4) and a pending-proposal-count nav badge (US-6.6), consuming the new Recategorization Review Component's endpoints. Follows this component's existing convention of one Frontend SPA component covering every page, not a component per page.
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds a "Backup Status" panel to the Review page (US-7.4), visually separate from the existing ProposalTable, consuming the new Backup Status Component's endpoint. Same convention — one Frontend SPA component, no new component for the panel.
- **Addendum (2026-08-08, Recurring Payments feature — Epic 8)**: Adds a Recurring Payments section to the Dashboard page (US-8.3: due/overdue/set-aside status, US-8.4/8.5: pending-match review, US-8.6: detection suggestions), plus a new attention-needed badge on the Dashboard nav link (US-8.7, same pattern as `PendingReviewBadge`). Same convention — one Frontend SPA component, no new component for the section.
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9, see `embedding-similarity-application-design-plan.md`)**: Adds an embedding-computed badge inline in the transaction list (US-9.1), consuming the extended Transaction Management Component's `embedding_status` field. Same convention — one Frontend SPA component, no new component for the badge.
- **Addendum (2026-08-16, Matching Precision Refinement, see `matching-precision-refinement-application-design-plan.md`)**: `ProposalTable`/`ProposalRow` on the Review page gain a third row kind — a two-candidate categorization disagreement (FR-MPR-9/10), with pick-one-or-reject actions instead of the existing single approve/reject — consuming the extended Recategorization Review Component's new `listPendingDisagreements`/`resolveDisagreement`/`rejectDisagreement` endpoints. Same convention — one Frontend SPA component, no new component for the row kind.
- **Addendum (2026-08-16, Configurable Application Settings feature, see `configurable-app-settings-application-design-plan.md`)**: Adds an "Application Settings" section to the existing `SettingsPage.tsx`, below the category-management section it already has (US-10.1), with an "Advanced" sub-heading (US-10.2), consuming the extended Configuration Component's new `listSettings`/`updateSetting`/`listSettingHistory`/`getRestartGuidance` endpoints. Same convention — one Frontend SPA component, no new component for the section.

---

## API Service Components

### Auth Component
- **Purpose**: Protect the entire application behind a single-user login.
- **Responsibilities**: Validate credentials, issue/validate session (e.g., session cookie or JWT), reject unauthenticated requests to any other API Service route.
- **Stories covered**: US-5.1

### Transaction Management Component
- **Purpose**: Owns all read/write access to transaction data on behalf of the user-facing UI.
- **Responsibilities**: List/filter/group/sort transactions; return a single transaction's detail (original + converted amount); apply manual category corrections and mark `category_source = manual`; trigger the retroactive-UNSURE-recategorization job (FR-5.4) after a correction; CSV export of the current filtered/grouped view.
- **Stories covered**: US-3.1, US-3.2, US-3.3, US-3.4, US-3.5, US-3.6, US-3.7
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)**: `listTransactions`/`getTransaction` now also return each transaction's `embedding_status`, read directly from the Shared DB (FR-7, US-9.1). Read-only — this component never calls the Vector Store Client or the embedding endpoint itself; it only surfaces a field the Ingestion Worker's new Embedding Manager Component writes.

### Dashboard/Insights Component
- **Purpose**: Serve aggregate, SGD-converted financial insight queries to the Frontend.
- **Responsibilities**: Category-trend aggregation; income-vs-expense/cash-flow aggregation; bank-level breakdown aggregation; apply date-range/currency filters; surface approximate-conversion / excluded-transaction disclosures per transaction set.
- **Stories covered**: US-4.1, US-4.2, US-4.3, US-4.4, US-4.5, US-4.6

### Ingestion Trigger & Status Component
- **Purpose**: The API Service's side of the async ingestion workflow — never performs extraction/categorization itself.
- **Responsibilities**: Accept a "start ingestion run" request from the Frontend and enqueue a run record for the Ingestion Worker; expose run status/progress (for polling) and run history for past runs, including per-file outcomes and failure reasons.
- **Stories covered**: US-1.2, US-1.5
- **Addendum (2026-08-01, during Unit 3 NFR Requirements)**: also owns the Google Drive OAuth connect/callback handshake (US-1.1) — added retroactively since Unit 3 (Ingestion Worker) has no browser-facing interface of its own to run an interactive OAuth flow; see `construction/api-service/code/api-layer-summary.md` and `audit.md` for the full history.

### Recategorization Review Component
- **Addendum (2026-08-02, Recategorization Review Panel feature — see `recategorization-review-application-design-plan.md`)**
- **Purpose**: Owns the human-in-the-loop review of proposed category changes that the Categorization Engine (Ingestion Worker) generates but doesn't auto-apply.
- **Responsibilities**: List pending proposals with enough context to judge them (candidate transaction, proposed category, match score/bucket, triggering correction); approve or reject a proposal individually or in bulk, writing the category directly to the transaction on approval; expose a pending count for the nav badge.
- **Interfaces**: New REST endpoints, consumed by the Frontend SPA's new Review page. Depends only on the Shared Data Store (reads/writes proposal rows and, on approval, the `transactions` table) — never calls the Ingestion Worker Service directly, matching this project's one hard architectural rule.
- **Stories covered**: US-6.4, US-6.5, US-6.6
- **Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: Also owns review of `CategorizationDisagreement` items (FR-MPR-9/10/11) — a distinct entity from `RecategorizationProposal` (two candidate categories, no triggering job), written by the Ingestion Worker's Categorization Engine, resolved here via pick-one-or-reject rather than approve/reject. The existing pending-count method now sums both entities' pending rows for one nav badge total. No bulk actions for disagreements (Design Decision 2) — each resolution is an individual, specific choice between two different categories.

### Backup Status Component
- **Addendum (2026-08-08, Nightly Transaction Backup feature — see `nightly-backup-application-design-plan.md`)**
- **Purpose**: Exposes the Ingestion Worker Service's nightly backup history/status to the Frontend, read-only.
- **Responsibilities**: Report the outcome of the most recent backup attempt (success, or failure with a failure category — `drive_connectivity` vs `other`) so the Review page's Backup Status panel can render the right message.
- **Interfaces**: New REST endpoint(s), consumed by the Frontend SPA's Backup Status panel. Depends only on the Shared Data Store (reads the new `backup_runs` table) — never calls the Ingestion Worker Service directly, matching this project's one hard architectural rule (same as the Recategorization Review Component).
- **Stories covered**: US-7.4

### Recurring Payments Component
- **Addendum (2026-08-08, Recurring Payments feature — Epic 8, see `recurring-payments-application-design-plan.md`)**
- **Purpose**: Owns the recurring-payments register, the human review side of the match workflow, and detection-suggestion triage.
- **Responsibilities**: CRUD for Recurring Payments (US-8.1); bulk CSV import with per-row error isolation (US-8.2); list/approve/reject pending matches (US-8.4); list, dismiss, or add-from detection suggestions (US-8.6); a status summary (due soon / overdue / pending / new suggestions counts) backing the Dashboard section and the nav badge (US-8.3, US-8.7).
- **Interfaces**: New REST endpoints under `/recurring-payments`, consumed by the Frontend SPA's Dashboard section. Depends only on the Shared Data Store — never calls the Ingestion Worker Service directly (same rule as Recategorization Review and Backup Status). Approve/reject writes are synchronous, direct DB writes (same precedent as Recategorization Review's approve/reject) — matching, trust-tracking, and detection remain exclusively the Worker's responsibility.
- **Stories covered**: US-8.1, US-8.2, US-8.3 (status data), US-8.4, US-8.6, US-8.7 (status data)

### Configuration Component
- **Purpose**: Manage user-editable configuration that isn't a secret.
- **Responsibilities**: List/add/rename/remove categories in the whitelist; validate that a category removal doesn't orphan existing transactions (block or require reassignment first).
- **Stories covered**: US-5.2
- **Addendum (2026-08-16, Configurable Application Settings feature — see `configurable-app-settings-application-design-plan.md`)**: Extended, not replaced — the same "manage non-secret user-editable configuration" charter now also covers the 35 in-scope application settings (Epic 10), not just the category whitelist. New responsibilities: list all in-scope settings with their current effective value, owning service, and standard/advanced classification (FR-CAS-1/2/3, US-10.1/10.2); validate a proposed new value against that setting's real type/range and, only if valid, write it to the new shared override-settings file (FR-CAS-4/5/8) — never the secrets-bearing root `.env`; record every successful write as a new `SettingChange` history row (FR-CAS-9, US-10.4); compute restart guidance for a just-changed setting — which container, the exact command, and (only for Ingestion-Worker-owned settings) a busy/idle read (FR-CAS-6/7, US-10.3, Key Design Resolution 2 below). Enforcement is allow-list-based, not denylist-based (see "Component Boundary Note" in the plan doc) — a request naming any of the 13 excluded secret/credential fields is rejected by construction, since those names simply aren't on the list `updateSetting`/`getSetting`/`listSettings` consult (NFR-CAS-2).

**Note**: Secrets configuration (US-5.3 — Google OAuth client, LLM API key, FX API key, DB credentials, JWT secret) remains environment-variable-based at container startup (NFR-4.1) and outside this component's reach entirely, even after the 2026-08-16 addendum above — both services still read their own required secrets from their own environment at boot and fail fast if missing. The addendum only moved the 35 *non-secret* settings from "env-var-only" to "editable via this component, env-var/override-file as the underlying mechanism."

---

## Ingestion Worker Service Components

### Drive Connector Component
- **Purpose**: All interaction with Google Drive.
- **Responsibilities**: Perform/refresh OAuth authentication; list PDF files in the configured folder; download file bytes for processing.
- **Stories covered**: US-1.1, part of US-1.2
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds write-side operations against the separate, dedicated backup Drive folder (distinct from the ingestion source folder): ensure the `backup` subfolder exists (creating it if needed), upload a file, list files in that subfolder, and delete a file. Reuses the same shared OAuth credential and the existing retry/transient-error pattern already used for list/download. Still "all interaction with Google Drive" — no new component needed.

### Backup Manager Component
- **Addendum (2026-08-08, Nightly Transaction Backup feature — see `nightly-backup-application-design-plan.md`)**
- **Purpose**: Owns the nightly transaction backup capability — a time-triggered concern, distinct from the queue-triggered Ingestion Orchestrator.
- **Responsibilities**: Detect when a backup is due (scheduled time reached, or a missed backup needs to catch up per FR-8); export a full snapshot of all transactions to CSV; upload it via the Drive Connector Component to the dedicated backup folder's `backup` subfolder; enforce retention (keep the 7 most recent, delete older, scoped only to this feature's own files); record the outcome (success, or failure with a failure category) for the Backup Status Component to read.
- **Stories covered**: US-7.1, US-7.2, US-7.3, US-7.4 (status-recording side)

### Duplicate Detection Component
- **Purpose**: Prevent reprocessing of already-imported statements.
- **Responsibilities**: Compute a hash of each downloaded PDF's raw bytes; check it against the processed-statements record; record the Drive file ID + hash once a statement is successfully processed.
- **Stories covered**: US-1.4

### Statement Extraction Component
- **Purpose**: Turn a PDF (bytes) into structured transaction rows.
- **Responsibilities**: OCR fallback for scanned/image PDFs; layout-adaptive, LLM-assisted parsing to identify transaction date/description/amounts, bank name, and currency; flag a statement as failed/needs-review when extraction confidence is too low.
- **Stories covered**: US-1.3

### Categorization Engine Component (pluggable — Question 3 = A)
- **Purpose**: Assign a whitelist category (or `UNSURE`) to a transaction.
- **Responsibilities**: Defines a `CategorizationStrategy` interface with two concrete strategies — **Similarity Matcher** (fuzzy-matches against past transactions, prioritizing manually-corrected precedent per FR-5.3) and **LLM Classifier** (fallback, constrained to the whitelist). Orchestrates the fallback chain (similarity → LLM → UNSURE) per FR-5.2. Also handles the retroactive re-scan of existing `UNSURE` transactions triggered by a manual correction (FR-5.4), invoked via an async job from the API Service.
- **Stories covered**: US-2.1, US-2.2, US-2.3, US-3.4 (retro edge case)
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: The retroactive re-scan (FR-5.4) is broadened and now split in two — searching `UNSURE` transactions *and* already-categorized transactions (US-6.1); auto-applying only very-high-confidence `UNSURE` matches as before (US-6.2), and always creating a pending proposal row (consumed by the new Recategorization Review Component) for everything else, including *every* match against an already-categorized transaction regardless of score (US-6.3). No new external dependency — reuses the existing similarity matcher.
- **Addendum (2026-08-08, Recurring Payments feature — Epic 8)**: Its similarity matcher gains a second caller — the new Recurring Payment Manager Component (below) — for matching a newly-persisted transaction against active Recurring Payments. No logic change to the Categorization Engine itself; this is purely a new call site (NFR-1).
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9, see `embedding-similarity-application-design-plan.md`)**: The Similarity Matcher strategy now tries embedding-based candidate search first (via the new Vector Store Client Component), falling back to the existing fuzzy-text approach only when no candidate clears the embedding-similarity threshold (FR-3, US-9.2) — the fuzzy-text matcher itself, including WR-20's normalization, is unchanged. Applies to both `categorize()` and `recategorizeUnsureFromPrecedent()` (FR-4). The existing amount-range gate and manual-source-precedence rule (WR-3) apply identically regardless of which method found the candidate (FR-5, NFR-1, US-9.3) — no separate, weaker check for the embedding path.
- **Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: The LLM Classifier strategy is no longer fallback-only — every transaction is classified by it (FR-MPR-1), via a new upfront, concurrent, per-file batch step (`classifyBatch`, Key Design Resolution 2) rather than a last-resort call inside `categorize()`. `categorize()`'s decision now combines the already-known LLM classification with similarity matching (FR-MPR-6): agreement auto-assigns as before; one confident signal with the other abstaining/absent auto-assigns the confident one directly; both confident and differing is a genuine disagreement, recorded as a new `CategorizationDisagreement` (Key Design Resolution 1) instead of a silent `UNSURE`. The embedded text for both this component's Vector Store Client calls and the Recurring Payment Manager's now includes a price-range bucket (FR-MPR-4), `embedding_similarity_threshold` is raised (FR-MPR-8), and candidate scoring gets a small boost when a candidate's known category agrees with the transaction's own LLM classification (FR-MPR-7) — exact per-call-site boost mechanics deferred to Functional Design (Design Decision 4). Each transaction's own LLM classification is now persisted (`Transaction.llm_suggested_category_id`, Key Design Resolution 3) so the retroactive re-scan can read it back later.
- **Addendum (2026-08-17, Categorization Model Fine-Tuning feature — see `categorization-model-finetuning-application-design-plan.md`, FR-CFT-9)**: The LLM Classifier strategy's prompt (both `classify` and `classifyBatch`) now also includes the transaction's `converted_amount_sgd` alongside `description` — so the live prompt shape matches what the new Model Training unit's Dataset Curator produces, keeping the fine-tuned model's training input and its real inference input identical. Bank name is deliberately excluded ("a very weak signal," per Resolved Decision 5). No change to the fallback chain, whitelist constraint, or `UNSURE` behavior.

### Currency Conversion Component
- **Purpose**: Compute a converted SGD amount for each transaction.
- **Responsibilities**: Fetch/cache historical FX rates per currency-pair/date from a public FX API; apply nearest-prior-date fallback when the exact date is unavailable and flag the result as approximate; leave a transaction unconverted (but still visible with its original amount) when no rate can be found at all.
- **Stories covered**: US-3.7, US-4.6

### Recurring Payment Manager Component
- **Addendum (2026-08-08, Recurring Payments feature — Epic 8, see `recurring-payments-application-design-plan.md`)**
- **Purpose**: Owns matching newly-ingested transactions against the Recurring Payments register, the review/trust/tolerance state progression, and periodic detection of untracked recurring charges.
- **Responsibilities**: Match a just-persisted transaction against active, unresolved-this-cycle Recurring Payments (reusing the Categorization Engine's similarity matcher, description/category + due-date window, amount as a loose guide per FR-5); create a pending match for a never-yet-approved Recurring Payment (FR-6), or auto-apply for a trusted one when the amount is within tolerance, else still create a pending match (FR-7); periodically scan transaction history for monthly-cadence repeating charges not yet covered by any Recurring Payment and record detection suggestions, respecting prior dismissals (FR-12/FR-13).
- **Stories covered**: US-8.4, US-8.5, US-8.6
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)**: `matchNewTransaction` and `runDetectionScan` both gain the same embedding-first-then-fuzzy-fallback behavior as the Categorization Engine (FR-4, US-9.2), via the new Vector Store Client Component — matching against a Recurring Payment's `name` (not another transaction, a separate vector-store collection). No change to the trust/tolerance state machine itself (Epic 8, unaffected) — only how a candidate match is *found*, not what happens once one is.
- **Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: The embedded text used by both methods' vector-store lookups now includes a price-range bucket (FR-MPR-4), and candidate scoring gets a small boost when a candidate's known category agrees with the newly-ingested transaction's own LLM classification, computed by the Categorization Engine's new batch-classification step (FR-MPR-7) — no disagreement-review branch here (Design Decision, FR-MPR-12: recurring-payment matching has no per-transaction category-assignment decision to disagree over). Exact boost mechanics per call site deferred to Functional Design.

### Vector Store Client Component
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9, see `embedding-similarity-application-design-plan.md`)**
- **Purpose**: All interaction with the vector database — the Drive Connector Component's equivalent role for embeddings.
- **Responsibilities**: Store an embedding vector for a transaction description or a Recurring Payment name (two logical collections); query nearest neighbors by cosine similarity, given a vector, a target collection, and result-filtering criteria (e.g. excluding the source transaction itself). Shared by the Categorization Engine, Recurring Payment Manager, and the Embedding Manager Component below — no other component talks to the vector DB directly.
- **Stories covered**: US-9.2 (as the mechanism enabling embedding-based candidate search)

### Embedding Manager Component
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9, see `embedding-similarity-application-design-plan.md`)**
- **Purpose**: Owns *when* a transaction's own embedding gets computed and persisted — a time/backlog-triggered concern, distinct from the query-time embedding computation the Categorization Engine and Recurring Payment Manager perform for themselves via the Vector Store Client (see the plan doc's "Key Design Resolution").
- **Responsibilities**: Call the user-managed oMLX endpoint (config-supplied base URL) to compute an embedding for a transaction's raw description (FR-9: no pre-normalization); store it via the Vector Store Client and update the transaction's `embedding_status`; process a bounded batch of pending transactions per poll cycle — this single mechanism serves both newly-ingested transactions (FR-6) and the one-time historical backfill (FR-11), since both are just "transactions with `embedding_status = pending`." Soft-fails per transaction/batch when the endpoint is unreachable (FR-10) — never blocks or fails an ingestion run.
- **Stories covered**: US-9.1, US-9.4, US-9.5
- **Addendum (2026-08-12, retroactively during Ingestion Worker Service Functional Design — see `ingestion-worker-embedding-similarity-functional-design-plan.md` and audit.md)**: The pending-backlog this component drains is not transactions-only. `RecurringPayment` rows also carry an `embedding_status` (Database `BR-25`, added retroactively at this stage) — the API Service's Recurring Payments Component sets it to `pending` on create or on any `name`-changing update, since API Service never calls the embedding endpoint/vector store itself. `processNextEmbeddingBatch()` drains both entity types' `pending` backlogs (one unified mechanism, per this component's original design principle) — see `services.md`'s corresponding addendum for the updated `poll_once()` due-check.

### Ingestion Orchestrator Component
- **Purpose**: The Worker Service's coordination layer — the only component that calls the others in sequence.
- **Responsibilities**: Pick up a queued run request; for each file: Drive Connector download → Duplicate Detection check → (if new) Statement Extraction → Categorization Engine → Currency Conversion → persist transactions; update run/file-level progress and status continuously so the API Service's polling reflects near-live state; ensure one file's failure doesn't abort the run (NFR-2.2).
- **Stories covered**: US-1.2, US-1.5 (progress/history data producer)

---

## Model Training (new unit, 2026-08-17, Categorization Model Fine-Tuning feature — see `categorization-model-finetuning-application-design-plan.md`)

Architecturally distinct from the API Service/Ingestion Worker/Frontend above: no docker-compose service, no persistent process, no polling loop. Two standalone CLI entry points, run manually, reading the Shared Data Store below read-only via the existing `transactagent_db` package (the same shared internal package the API Service and Ingestion Worker already depend on for models — reused rather than duplicated, per NFR-CFT-1's environment-isolation requirement applying only to the *heavyweight ML* dependencies, not the DB access layer).

### Dataset Curator Component
- **Purpose**: Turn labeled transactions into a trustworthy, exportable fine-tuning dataset.
- **Responsibilities**: Select transactions where `category_source='manual'`, OR (`category_source='similarity'` AND referenced by an `approved` `recategorization_proposals` row) — FR-CFT-1; for each, emit `description` + `converted_amount_sgd` + target category name + source `transaction_id` — FR-CFT-2; split into train/held-out validation sets — FR-CFT-3; write both splits to disk in a shape mlx-tune's `SFTTrainer` can consume directly — FR-CFT-4. Deterministic and re-runnable (NFR-CFT-4) — same DB state always produces the same output.
- **Stories covered**: N/A (User Stories skipped for this feature — developer/ML tooling)

### Fine-Tuning Trainer Component
- **Purpose**: Fine-tune the categorization model against a curated dataset and judge whether it actually improved.
- **Responsibilities**: Load `mlx-community/gemma-4-26b-a4b-it-4bit` via mlx-tune's `FastLanguageModel`, attach LoRA adapters, fine-tune via `SFTTrainer` against the Dataset Curator's training split — FR-CFT-5; log run configuration, metrics, and artifacts to ClearML (hosted SaaS) — FR-CFT-6; evaluate against the held-out validation split, reporting accuracy/confusion-matrix and agreement-rate versus the current live model's predictions on the same inputs, both to ClearML — FR-CFT-7; save the resulting artifact (LoRA adapter and/or merged model) locally — FR-CFT-8. No deployment/conversion step — out of scope per Resolved Decision 7.
- **Correction (2026-08-17, found at Functional Design, MTR-7)**: FR-CFT-7b's "live model" comparison does not call into API Service or Ingestion Worker Service — no such on-demand-classification endpoint exists anywhere in this codebase. `evaluate()` instead independently replicates the exact live prompt template (WR-34) and calls the same oMLX server directly via its own HTTP client, reading `OPENROUTER_BASE_URL`/`OPENROUTER_MODEL` from local config. Model Training remains a true leaf/offline component with zero dependency on the other 4 units' code.
- **Correction (2026-08-17, found at Code Generation)**: mlx-tune's plain-text `FastLanguageModel`/`SFTTrainer` (this component's originally-described API) does not apply to `gemma-4-26b-a4b-it-4bit` — Gemma 4 is a VLM even for text-only tasks, per mlx-tune's own real examples targeting this exact model. `FastVisionModel`/`VLMSFTTrainer`/`VLMSFTConfig` used instead (`finetune_vision_layers=False` for this text-only use). See `business-logic-model.md`'s full correction note.
- **Stories covered**: N/A (User Stories skipped for this feature — developer/ML tooling)

---

## Shared Data Store

### PostgreSQL-class Database (shared, not a "component" with behavior — see NFR Requirements for exact engine choice)
- Owns: users/credentials, transactions, processed-statements, category whitelist, ingestion runs (job/status/history), FX-rate cache.
- Both the API Service and the Ingestion Worker Service connect to it directly with their own data-access code — they are **not** coupled via a shared in-process library (they're separate deployables per Question 1 = B), only via the shared schema (a data contract, documented in `component-dependency.md`).
- **Addendum (2026-08-02, Recategorization Review Panel feature)**: Adds a recategorization-proposal record, child of the existing `recategorization_jobs` row — written by the Ingestion Worker's Categorization Engine, read/updated by the API Service's new Recategorization Review Component. Exact table shape is a Functional Design (Database unit) decision.
- **Addendum (2026-08-08, Nightly Transaction Backup feature)**: Adds a `backup_runs` tracking table — written by the Ingestion Worker's new Backup Manager Component, read by the API Service's new Backup Status Component. Exact table shape is a Functional Design (Database unit) decision.
- **Addendum (2026-08-08, Recurring Payments feature — Epic 8)**: Adds a recurring-payments register table, a per-cycle match table, and a detection-suggestion table — the register and match/suggestion resolution (approve/reject/dismiss/add) are written by the API Service's Recurring Payments Component; match/suggestion creation and the register's `is_trusted` flag are written by the Ingestion Worker's Recurring Payment Manager Component. Exact table shapes are a Functional Design (Database unit) decision.
- **Addendum (2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)**: Adds an `embedding_status` field to `transactions` — written by the Ingestion Worker's new Embedding Manager Component, read by the API Service's Transaction Management Component (FR-7). Exact field shape (enum vs. timestamp-based) is a Functional Design (Database unit) decision.
- **Addendum (2026-08-16, Matching Precision Refinement feature — see `matching-precision-refinement-application-design-plan.md`)**: Adds an `llm_suggested_category_id` field to `transactions` (Key Design Resolution 3) — written once by the Ingestion Worker's Categorization Engine at ingestion time, read by the same component later during the retroactive re-scan's score-boost logic. Adds a new `CategorizationDisagreement` table (Key Design Resolution 1) — written by the Ingestion Worker's Categorization Engine, read/resolved by the API Service's extended Recategorization Review Component. Deliberately a new entity, not an extension of `recategorization_proposals` — see the plan doc for why. Exact table shapes are a Functional Design (Database unit) decision.
- **Addendum (2026-08-16, Configurable Application Settings feature — see `configurable-app-settings-application-design-plan.md`)**: Adds a new `setting_changes` table (Key Design Resolution 4) — written and read only by the API Service's Configuration Component; the Ingestion Worker Service has no involvement with it. Busy/idle status for FR-CAS-7 (Key Design Resolution 2) deliberately needs **no** new table — it's answered by a read-only query against the existing `ingestion_runs`/`recategorization_jobs` tables' `status = 'running'` state, already written by the Ingestion Orchestrator today. Exact `setting_changes` table shape is a Functional Design (Database unit) decision.
- **Addendum (2026-08-17, Categorization Model Fine-Tuning feature — see `categorization-model-finetuning-application-design-plan.md`)**: No new tables. The new Model Training unit's Dataset Curator Component reads `transactions`, `recategorization_proposals`, and `categorization_disagreements` **read-only** — the first table with a write dependency-free consumer this project has had (every prior addendum above described a writer/reader pair between the two existing services; Model Training only ever reads). Reuses the existing `transactagent_db` package rather than introducing a second, parallel data-access layer.

### Vector Store (new, 2026-08-11, Local Embedding-Based Semantic Similarity feature — Epic 9)
- A **separate, dedicated vector database service** (product TBD at NFR Requirements) — not part of the PostgreSQL-class Shared Data Store above. Holds two logical collections: transaction-description embeddings and recurring-payment-name embeddings.
- Written to and queried **only by the Ingestion Worker Service**, via the new Vector Store Client Component. The API Service never connects to it directly — consistent with this project's "no direct API-Service-to-Worker-owned-thing" pattern (same as `backup_runs`, recategorization proposals, etc., which the API Service only ever reads via its own Postgres connection, never by reaching into a Worker-owned datastore).
