# Requirements: Matching Precision Refinement

## Intent Analysis

- **User request**: "The embedding matching is too sensitive. Can i suggest some refinements. During ingestion: for each transaction, ask the local `mlx-community/gemma-4-26b-a4b-it-4bit` model on its category (batch if more effective — 'this model seems to be able to get it correct most of the times'). During matching: (1) include the price range in the embedding, (2) increase the threshold a little, (3) somehow use the information from during ingestion." — followed by answers to `matching-precision-refinement-questions.md` and `matching-precision-refinement-clarification-questions.md`.
- **Request type**: Enhancement to existing behavior — a follow-up refinement to the just-completed Local Embedding-Based Semantic Similarity feature (Epic 9), plus a new review-surface addition for the disagreement case it introduces.
- **Scope estimate**: Multiple components — `ingestion-worker` (categorization pipeline behavior, embedding text, matching scoring), `database` (new field(s)/entity to carry two candidate categories), `api-service` (expose/resolve disagreement items), `frontend` (surface disagreement items on the existing Review page).
- **Complexity estimate**: Moderate — builds heavily on existing infra (the LLM classifier client, the embedding/vector-store subsystem, the `ReviewPage`/`ProposalTable` review pattern from Epic 6) rather than introducing new tech, but changes categorization decision semantics and adds a new reviewable-item shape.

## Current Behavior (baseline, confirmed against live code — see audit.md)

- `categorization/service.py`'s `categorize()` fallback chain: **embedding match → fuzzy-text match → LLM (`OPENROUTER_BASE_URL`/`OPENROUTER_MODEL`) → UNSURE**. The LLM call only happens when both similarity methods find nothing — it is a last resort, not run for every transaction.
- `embedding/service.py` embeds only the transaction `description` (or recurring payment `name`) via `client.compute_embedding` — no price/amount signal in the embedded text.
- `embedding_similarity_threshold` = 0.75 (cosine, 0.0–1.0 scale), used both by `find_similar_transaction_via_embedding` (categorization) and by the recurring-payment matching paths in `recurring_payments/service.py`.
- `OPENROUTER_BASE_URL` is already pointed at a local OpenAI-compatible model server (a `gemma-4-12B-it-4bit` model was noted running there per project history).
- The Review page (`ReviewPage`/`ProposalTable`/`ProposalRow`, Epic 6) already implements an approve/reject/pick pattern for `RecategorizationProposal` rows, but that entity is designed around a single proposed category per row, created by a manual-correction-triggered re-scan job — not by ingestion-time classification.
- Today's plain `UNSURE` transactions show no suggested candidates at all — a user manually picks a category from a dropdown with no hints.

## Resolved Decisions (from clarifying questions)

| # | Decision | Answer |
|---|---|---|
| 1 | LLM classification scope | Runs for **every** transaction at ingestion time, always — not fallback-only. |
| 2 | Priority when signals agree/disagree | See Clarification 1 below — refined into FR-MPR-6. |
| 3 | Model hosting | Same local server as today's `OPENROUTER_BASE_URL` — just change `OPENROUTER_MODEL` to `mlx-community/gemma-4-26b-a4b-it-4bit`. No new base-url setting. |
| 4 | Batching mechanism | Concurrent individual calls (today's one-transaction-per-prompt format, fired in parallel) — not a single multi-transaction prompt. |
| 5 | Price-bucket boundaries | Configurable (env-tunable), not hardcoded to the illustrated example. |
| 6 | Re-embedding existing rows | Yes — existing already-embedded transactions/recurring payments are re-embedded so the vector store is consistent with the new price-bucket-inclusive text. |
| 7 | Threshold increase amount | Left to the implementation to pick a reasonable value and document the rationale (Functional/Code Generation), same as how `similarity_threshold`/`recategorization_auto_apply_threshold` were originally tuned. |
| 8 | How the LLM category is used during matching | Soft signal — a small score boost when the candidate's category agrees with the transaction's own LLM classification; disagreement does not reject the candidate, it just doesn't get the boost. |
| 9 | Scope: categorization only vs. also recurring payments | Both — price-bucket embedding and the soft agreement-boost apply to transaction categorization AND recurring-payment matching/detection. |
| 10 (Clarification 1) | What counts as a "disagreement" | Only when BOTH similarity matching and the LLM produce a real category AND those categories differ. If only one signal is confident (the other abstains/finds nothing), the confident signal wins and is auto-assigned directly — not treated as a disagreement. |
| 11 (Clarification 2) | Where disagreements are surfaced | Routed through the existing `/review` page as a new kind of reviewable item (reusing the `ProposalTable`/`ProposalRow` pattern), not left as a bare `UNSURE` transaction. |

## Functional Requirements

- **FR-MPR-1**: At ingestion time, every transaction SHALL be classified by the local LLM (model `mlx-community/gemma-4-26b-a4b-it-4bit`), using the same category whitelist + `UNSURE`-on-abstain contract already enforced by `llm_classifier.classify` — not only when similarity matching fails.
- **FR-MPR-2**: The LLM classification call SHALL reuse the existing OpenAI-compatible client configuration (`OPENROUTER_BASE_URL`), with `OPENROUTER_MODEL` changed to the new model name — no new base-url/endpoint setting is introduced for this call.
- **FR-MPR-3** *(revised 2026-08-16, see "Post-Approval Change" below)*: When multiple transactions in the same ingestion pass need LLM classification, descriptions SHALL be grouped into batches (size configurable) and each batch classified in a single prompt/response; batches themselves SHALL be issued concurrently, bounded by a configurable cap (NFR-MPR-1). A description a batch's response didn't yield a valid answer for SHALL fall back to an individual classification call, not the whole batch it was part of.
- **FR-MPR-4**: The text embedded for both transactions and recurring payments SHALL include a price-range bucket alongside the existing description/name (e.g. `"Coffee Bean And Tea Leaf | $6 to $10"`).
- **FR-MPR-5**: Price-range bucket boundaries SHALL be configurable (env-tunable), not hardcoded.
- **FR-MPR-6**: `categorize()`'s decision, combining similarity matching and the always-on LLM classification (FR-MPR-1), SHALL follow:
  - Similarity produces a category **and** the LLM independently produces the **same** category → auto-assign it (unchanged end result from today, `category_source = similarity`).
  - Similarity produces a category but the LLM abstains (`UNSURE`), **or** the LLM produces a category but similarity finds no match at all → the confident signal wins and is auto-assigned directly (not a disagreement).
  - Both similarity and the LLM produce a category **and they differ** → genuine disagreement: neither is auto-assigned (see FR-MPR-9/10).
  - Both abstain / find nothing → `UNSURE`, unchanged from today.
- **FR-MPR-7**: During embedding-based match candidate evaluation — for both transaction categorization (`find_similar_transaction_via_embedding`, `recategorize_unsure_from_precedent`) and recurring-payment matching/detection — when a candidate's known category agrees with the transaction's own LLM classification (FR-MPR-1), the match/similarity score SHALL receive a small boost; disagreement SHALL NOT reject the candidate outright, it simply does not receive the boost.
- **FR-MPR-8**: `embedding_similarity_threshold` SHALL be raised above its current value of 0.75; the exact new value and rationale are determined during Functional/Code Generation for the Ingestion Worker unit.
- **FR-MPR-9**: A genuine disagreement (FR-MPR-6, third bullet) SHALL be recorded as a new reviewable item carrying **both** candidate categories (the similarity-sourced one and the LLM-sourced one) and left unassigned (`UNSURE`) until resolved.
- **FR-MPR-10**: Disagreement items (FR-MPR-9) SHALL be surfaced on the existing `/review` page, reusing the `ProposalTable`/`ProposalRow` interaction pattern, extended to a choose-one-of-two action (pick the similarity candidate, pick the LLM candidate, or reject/leave `UNSURE`) rather than a single approve/reject.
- **FR-MPR-11**: Resolving a disagreement item (picking one of the two candidates) SHALL write the chosen category to the transaction, consistent with how existing proposal approval writes `category_id`/`category_source`.
- **FR-MPR-12**: FR-MPR-6/9/10/11 apply to transaction categorization only. Recurring-payment matching has no per-transaction category-assignment decision to disagree over — it only gains FR-MPR-4 (price-bucket embedding) and FR-MPR-7 (soft agreement-boost using the LLM classification of the transactions being matched); it does not gain a disagreement-review surface.

## Non-Functional Requirements

- **NFR-MPR-1 (Latency/load)**: The always-on per-transaction LLM classification (FR-MPR-1) adds load to ingestion; concurrency (FR-MPR-3) SHALL be bounded by a configurable cap (consistent with this project's existing tunable-settings convention in `config.py`), not unbounded parallelism.
- **NFR-MPR-2 (Graceful degradation)**: Consistent with the project's existing soft-dependency pattern for the LLM/embedding subsystems (Epic 9's WR-25 framing) — if the local LLM classification endpoint is unavailable, ingestion SHALL degrade gracefully (the transaction falls through to `UNSURE` via existing fallback semantics) rather than blocking ingestion.
- **NFR-MPR-3 (Re-embed mechanism reuse)**: The re-embed sweep for existing rows (Decision 6) SHALL reuse the existing pending-batch poll mechanism (`process_next_embedding_batch`) by resetting `embedding_status` to `pending`, rather than a new one-off backfill script.
- **NFR-MPR-4 (Configurability)**: All new/changed thresholds and bucket boundaries SHALL be env-configurable in `config.py`/`.env.example`, matching the project's existing tunable-settings convention (e.g. `embedding_similarity_threshold`, `similarity_threshold`).
- **NFR-MPR-5 (Testability)**: Given this project's established practice (all units have real test suites, verified against live containers before completion), the new disagreement-detection logic, score-boost logic, and Review-page choose-one-of-two flow SHALL have test coverage at the layer they're implemented in, and SHALL be verified against the live stack before this is considered done.

## Deferred to Application/Functional Design (not requirements-level decisions)

- Whether the two-candidate disagreement item (FR-MPR-9) is implemented by extending `RecategorizationProposal` (e.g. a nullable second category column + a new `source_bucket` value, with `job_id` made nullable or a synthetic job created) or by a new, parallel table/entity. A new/extended entity is the more decoupled fit given `RecategorizationProposal` is otherwise tied to a `RecategorizationJob` (a manual-correction event) that doesn't exist for this ingestion-time origin — but this is a technical/schema call for Application Design, not Requirements.
- The exact magnitude of the FR-MPR-7 score boost and the exact new `embedding_similarity_threshold` value (FR-MPR-8).
- The exact price-bucket boundary defaults and their env-variable names.
- The exact concurrency cap value (NFR-MPR-1).
- Exact `ProposalRow` UI treatment for the choose-one-of-two action (FR-MPR-10) — e.g. two labeled buttons vs. a radio choice plus a single confirm.

## Out of Scope

- No change to the LLM classification's whitelist/`UNSURE` contract itself (WR-4) — only when it runs and how its result is used changes.
- No change to the existing manual-correction-triggered retroactive re-scan (`recategorize_unsure_from_precedent`, Epic 6/9) beyond it also benefiting from FR-MPR-4/7/8 as part of the shared embedding/matching infrastructure.
- No new external integration — the new model is served by the same local, already-configured OpenAI-compatible endpoint category as today's fallback LLM.

## Post-Approval Change (2026-08-16, discovered during Build and Test): FR-MPR-3 Batching Mechanism Reversed

Original Question 4 (resolved answer: B) chose concurrent individual calls (one HTTP request per description) over a single multi-transaction prompt. Live-testing `classify_batch` against the user's real local model server (during this feature's Build and Test stage) surfaced the real concern it was meant to avoid guessing at: a file with many transactions means many simultaneous HTTP requests to a single local model server, which is a materially different load profile than a hosted, horizontally-scaled API. The user asked to revisit this after seeing it live.

**New resolved decisions** (replacing Question 4's original answer):
- Descriptions are grouped into batches of `llm_classification_batch_size` (default 10, env-configurable) and each batch is classified in a single prompt, expecting a JSON array response (one category per description, same order).
- Batches themselves still run concurrently, bounded by the existing `llm_classification_concurrency` (default 5) — combining both refinements rather than choosing one over the other: at most `concurrency` HTTP requests in flight at once, each covering up to `batch_size` transactions.
- If a batch's response is unparseable, too short, or contains an invalid entry for a specific description, only those specific descriptions fall back to an individual `classify()` call (concurrently, same cap) — not the whole batch, so one bad entry doesn't discard correctly-classified siblings.

Live-verified against the real running oMLX server (not simulated): a 6-item batch returned a fully valid JSON array in 1.04s, including correctly answering `UNSURE` for a deliberately ambiguous description; a 12-item `classify_batch` call (2 batches of 10+2, both real user categories from the live database) completed in 2.52s with all 12 correctly classified, vs. an estimated ~11s for 12 sequential individual calls. FR-MPR-3, WR-27 (Ingestion Worker business-rules.md), and Application Design's "Key Design Resolution 2" are all updated in place to reflect this — this document's own FR-MPR-3 wording ("issued concurrently, bounded by NFR-MPR-1") is superseded by the two-phase batched-then-fallback design described above.
