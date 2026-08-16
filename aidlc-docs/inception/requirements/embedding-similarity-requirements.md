# Requirements: Local Embedding-Based Semantic Similarity Matching

Tracked as a Post-Completion change, same pattern as Epics 6/7/8 and the just-completed Similarity-Matching
Normalization change. Base project status unchanged: COMPLETE. Feature-scoped, does not modify the
project-wide `requirements.md`. On branch `feature/recurring-payments-budget-alerts`.

Layered on top of WR-20 (reference-code-noise normalization, just shipped): WR-20's normalized fuzzy-text
matcher (`find_best_match`, `rapidfuzz`) becomes a **fallback** path under this change (FR-3), not replaced
or removed — see FR-3 and FR-9.

## Intent Analysis

- **User Request** (paraphrased from a multi-turn conversation, then formalized via a 10-question round plus
  2 rounds of clarification): The user felt the regex-based WR-20 normalization fix, while working, wasn't
  "good enough" as a general solution and asked about using an LLM instead. After discussing that inline
  per-candidate LLM/embedding calls would violate the existing pure-function/no-I/O performance constraint
  (NFR-1/NFR-3 of the WR-20 requirements) regardless of local vs. hosted, the user proposed running a small
  local embedding model (`google/embeddinggemma-300m`) via a local inference server, computing and storing
  embeddings at ingestion time (batched/async), surfacing a transaction-list badge, and using the resulting
  vector store for similarity checks during categorization/recategorization.
- **Request Type**: New Feature / Architectural Enhancement to existing business logic (extends FR-5.2/WR-3,
  layers on top of WR-20)
- **Scope Estimate**: **Multiple Components** — touches Database (new tracking fields), Ingestion Worker
  Service (new Embedding component, backfill job, extended Categorization Engine + Recurring Payment
  Manager), API Service (expose embedding-status for the badge), and Frontend SPA (render the badge). This
  is broader than WR-20, which was single-component.
- **Complexity Estimate**: Complex — new external local-inference dependency, a new vector-store
  infrastructure decision, a one-time historical backfill (an explicit departure from this project's
  established forward-only pattern), and a change to the categorization decision order across two existing
  features (Categorization Engine and Recurring Payment Manager).

## Requirements Depth
**Comprehensive** — new infrastructure/tech-stack decision, new component, user-facing change, multi-unit
scope, and a decision that alters core existing business logic (WR-3/WR-16/WR-19 matching order). Resolved
via a 10-question round (`embedding-similarity-questions.md`) plus 2 rounds of targeted clarification
(`embedding-similarity-clarification-questions.md`) — one to identify the actual runtime tool by name (it
turned out to be "oMLX", a real product, verified via independent web sources — not the two options
originally offered), one to resolve a deployment-topology consequence discovered only once the runtime was
identified (oMLX is macOS/Apple-Silicon-native and cannot run inside this project's existing Linux Docker
containers).

## Functional Requirements

- **FR-1**: The Ingestion Worker Service computes a semantic embedding for each transaction's description
  using a local embedding model (`google/embeddinggemma-300m`), served by **oMLX** — a local inference
  server the user installs and runs themselves, outside `docker-compose` (not managed by this project's
  deployment). The Ingestion Worker Service is configured with the endpoint's base URL (a new config value,
  exact key name decided at Code Generation, same pattern as existing `OPENROUTER_*`/`GEMINI_*` config).
- **FR-2**: Computed embeddings are stored in a **dedicated vector database service**, added as a new
  `docker-compose` service (unlike the embedding runtime itself, a standard vector DB is containerizable on
  Linux — the specific product, e.g. Qdrant/Chroma/Milvus, is deferred to NFR Requirements).
- **FR-3**: The existing fuzzy-text Similarity Matcher (`find_best_match`, WR-3, extended by WR-20) is
  **not removed**. It becomes the fallback: for every comparison currently performed by the fuzzy-text
  matcher, the system first attempts embedding-based similarity search against the vector store; if no
  candidate clears the embedding-similarity threshold (FR-8), the system falls back to the existing
  fuzzy-text matcher exactly as it behaves today (including WR-20's normalization, unchanged).
- **FR-4**: This embedding-first-then-fuzzy-text-fallback approach applies everywhere the fuzzy-text
  matcher is currently invoked: the Categorization Engine (`categorize`, `recategorize_unsure_from_precedent`
  — FR-5.2/FR-5.4/WR-9/WR-10), the Recurring Payment Manager's transaction-matching (WR-16), and the
  Recurring Payment Detection Scan (WR-19).
- **FR-5**: When an embedding-based candidate does clear the threshold, it is used exactly as a
  fuzzy-text-sourced match would be today — subject to the same manual-source precedence rule (WR-3) and
  the same amount-range gate (`amounts_in_range`, NFR-2 of the WR-20 requirements) — see NFR-1 below. This
  is not a new, parallel decision path; it's the same decision logic fed by a different candidate-scoring
  method.
- **FR-6**: Embedding computation happens asynchronously and may be batched, decoupled from the main
  statement-ingestion run. Embeddings are **not** required for a statement-processing run to be marked
  `completed` (unlike extraction/categorization) — a transaction may appear in the system before its
  embedding is ready.
- **FR-7**: Each transaction exposes an embedding-status indicator (a new field, surfaced by the API Service
  and rendered as a badge in the Frontend transaction list) meaning **"this transaction's embedding has
  been computed and stored"** — a processing-status indicator only. It does **not** claim a similar
  transaction was found; it does not indicate anything about categorization confidence or precedent
  matches. (This is a deliberate, narrower meaning than "precedent found" — confirmed via clarifying
  question, consistent with FR-6's async/eventually-consistent model: the badge is how a user can tell
  whether the background job has caught up with a given transaction yet.)
- **FR-8**: A new, separate, configurable cosine-similarity threshold governs the embedding-based matching
  step (exact value tuned at Code Generation/testing, same pattern as `similarity_threshold`). This is
  independent of and does **not** replace `similarity_threshold` (85.0) or
  `recategorization_auto_apply_threshold` (97.0), which remain exactly as they are and continue to govern
  the fuzzy-text fallback path only.
- **FR-9**: Description text is fed to the embedder **raw** — WR-20's reference-code-noise regex
  normalization is **not** applied before embedding (a semantic embedding model is expected to be
  reasonably robust to this kind of noise on its own). WR-20's normalization remains exactly as shipped,
  applying only within the fuzzy-text fallback path (FR-3), unchanged.
- **FR-10**: If the local embedding endpoint is unavailable, or a call to it fails, the affected
  transaction(s) simply have no embedding (no badge, FR-7) — statement ingestion and categorization proceed
  unaffected, falling through to the fuzzy-text matcher (FR-3) exactly as if embedding-based matching found
  no candidate. This is a soft dependency, not a hard requirement for a successful ingestion run (contrast
  with WR-1's extraction-failure criteria, which this explicitly does not extend).
- **FR-11**: A **one-time historical backfill** computes embeddings for all existing transactions as part of
  this change — an explicit, deliberate departure from this project's established forward-only pattern (used
  for WR-20 and Epic 8's similarity-matcher reuse), justified because embedding-based precedent search is
  only useful once there is history to compare against. Exact triggering mechanism (automatic on deploy vs.
  a manually-invoked one-time job) is deferred to Functional Design/NFR Design.

## Non-Functional Requirements

- **NFR-1 (carried over, not weakened)**: The amount-range gate (`amounts_in_range`) that protects against
  the AXS PTE LTD-style false-positive incident (near-identical text, wildly different amounts) MUST
  continue to apply identically to the embedding-based matching path — it is not bypassed or weakened by
  introducing a new scoring method. This is a hard requirement, not a documented assumption, given this
  project's history with that specific regression.
- **NFR-2**: The exact vector database product (FR-2) is deferred to NFR Requirements, evaluated against
  this project's established preference for minimal infrastructure footprint (precedent: Database unit's
  "no separate broker" decision) balanced against genuine vector-search/ANN capability needs.
- **NFR-3**: The embedding-computation call is I/O-bound (network call to the external oMLX endpoint) and is
  explicitly **not** a pure function — unlike WR-20's `normalize_reference_noise`, it is out of scope for
  this project's Partial Property-Based-Testing convention. Any *pure* logic split out of the embedding path
  (e.g. a threshold-comparison/fallback-decision function) should still receive PBT coverage where
  applicable, consistent with the existing Partial PBT scope.
- **NFR-4**: The backfill job (FR-11) must be safe to interrupt and resume/re-run without duplicating work or
  corrupting state (idempotent), consistent with this project's existing migration-safety bar (precedent:
  Database unit's auto-migrate-with-advisory-lock design).
- **NFR-5**: The new local-inference dependency (oMLX) is explicitly out of this project's automated
  deployment (`docker-compose up`) — it is a manually-managed, host-native prerequisite the user runs
  themselves. This must be clearly documented as a new setup step, distinct from every other component of
  this stack, which remains fully containerized.

## Business Context

- **Goal**: Improve categorization/recategorization precedent-matching accuracy beyond what fuzzy text
  matching (even with WR-20's noise normalization) can achieve, by using semantic similarity — robust to
  paraphrasing, reordering, and noise shapes that a regex-based approach can't anticipate — while keeping
  the existing fuzzy-text approach as a safety-net fallback rather than removing a working, well-tested
  mechanism outright.
- **Success Criteria**: Embedding-based matching produces correct precedent matches (same-payee pairs
  matching, different-payee pairs not matching) at least as reliably as the current fuzzy-text approach on
  the same diagnosis examples used for WR-20, without regressing the AXS-incident amount-gate protection
  (NFR-1) or the manual-source-precedence rule (WR-3). The transaction-list badge accurately reflects
  embedding-computation status. The one-time backfill completes for all existing transactions without data
  loss or duplication.

## Documented Assumptions (flagged, not further questioned)

1. **Runtime identity**: The user's originally ambiguous "olmx"/"omlx" was investigated (WebSearch, not a
   direct fetch of the pasted referral-style URL) and confirmed to be **oMLX** (omlx.ai) — a real, actively
   discussed local MLX-based inference server for Apple Silicon, verified via independent third-party
   sources (GitHub, published write-ups), not a scam or fabricated tool.
2. **Deployment topology**: oMLX cannot run inside this project's existing Linux Docker containers (no
   Apple Silicon acceleration inside Docker Desktop's Linux VM). Resolved: the user will install and run
   oMLX themselves outside `docker-compose`; the Ingestion Worker Service only needs a config value pointing
   at its endpoint. No `docker-compose` service is added for the embedding runtime itself (contrast with
   FR-2's vector DB, which is containerizable and does get a new service).
3. **Manual-source precedence and the amount gate carry over unchanged** to the embedding-matching path
   (FR-5, NFR-1) — a natural extension of already-established WR-3 behavior, not re-litigated via a new
   question given the low risk of misreading this as anything other than "same decision logic, new scoring
   input."
4. Exact config key names, the specific vector DB product, the new cosine-similarity threshold's value, and
   the backfill job's triggering mechanism are all deferred to NFR Requirements/Functional Design/Code
   Generation, consistent with this project's established pattern of not hardcoding such decisions into the
   requirements document itself.

## Out of Scope

- Removing or replacing the fuzzy-text Similarity Matcher (`find_best_match`) or WR-20's normalization —
  both remain, as the fallback path (FR-3, FR-9).
- Changing `similarity_threshold` (85.0) or `recategorization_auto_apply_threshold` (97.0) — both continue
  to govern the fuzzy-text fallback path only (FR-8).
- Any UI beyond the embedding-status badge itself (FR-7) — no new review/approval workflow, no manual
  override UI for embedding-based matches in this iteration.
- Containerizing the embedding runtime itself — explicitly a host-native, user-managed prerequisite (NFR-5,
  Documented Assumption #2).
