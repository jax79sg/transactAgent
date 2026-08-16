# Matching Precision Refinement — Clarifying Questions

Context for these questions (current behavior, confirmed by reading the code):
- `categorization/service.py`'s `categorize()` fallback chain today is: **embedding match → fuzzy-text match → LLM (OpenRouter-compatible, `OPENROUTER_BASE_URL`/`OPENROUTER_MODEL`) → UNSURE**. The LLM only runs when both similarity methods find nothing.
- `embedding/service.py` embeds only the transaction `description` (or recurring payment `name`) — no price/amount signal.
- `embedding_similarity_threshold` = 0.75 (cosine, 0.0–1.0 scale). `embedding_top_k` = 5. `embedding_batch_size` = 50 (this governs the *embedding-computation* poll batch, not LLM calls).
- The existing `OPENROUTER_BASE_URL` is already pointed at a local model server per project history (a `gemma-4-12B-it-4bit` model was noted running there).
- Embedding-based matching is used in two places: transaction categorization (`find_similar_transaction_via_embedding`, `recategorize_unsure_from_precedent`) and recurring-payment matching/detection (`recurring_payments/service.py`).

Please answer each question below by filling in the letter after `[Answer]:`. If none of the options fit, choose the "Other" option and describe your preference.

## Question 1
Should the local LLM (`mlx-community/gemma-4-26b-a4b-it-4bit`) classify **every** transaction at ingestion time, or only run as today's last-resort fallback (just swapping which model answers)?

A) Every transaction gets classified by this LLM at ingestion time, always — even if embedding/fuzzy matching already found a category, the LLM result is still computed and stored as extra data

B) Keep it fallback-only, same as today (only called when embedding + fuzzy matching both find nothing) — just point that existing fallback call at the new model

C) Other (please describe after [Answer]: tag below)

[Answer]: A 

## Question 2
If Question 1 is "A" (LLM always runs), and a transaction also gets a match from embedding/fuzzy similarity, which result should win as the transaction's actual assigned category?

A) Similarity result wins first, same priority order as today (embedding → fuzzy → LLM → UNSURE) — the LLM classification is computed for every transaction but only used as the assigned category when nothing else matched; otherwise it's stored purely as a signal for matching (see Question 8)

B) LLM result always wins and becomes the primary category source — similarity matching is then only used to find a precedent transaction / decide auto-apply confidence, not to pick the category itself

C) If LLM and similarity disagree, treat it as UNSURE and flag for review rather than picking either automatically

D) Other (please describe after [Answer]: tag below)

[Answer]: C. And during review offer both options so human can decide. 

## Question 3
Is `mlx-community/gemma-4-26b-a4b-it-4bit` served by the **same** local server currently configured via `OPENROUTER_BASE_URL`/`OPENROUTER_MODEL` (i.e. just change `OPENROUTER_MODEL` to this new model name), or a **different** server/endpoint?

A) Same server — just change `OPENROUTER_MODEL` to `mlx-community/gemma-4-26b-a4b-it-4bit`, reuse the existing config as-is

B) Different server — needs its own separate base URL / config (distinct from `OPENROUTER_BASE_URL`), similar to how `EMBEDDING_BASE_URL` is already kept separate from `OPENROUTER_BASE_URL`

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 4
"Batch it if it's more effective" — how should batching actually be implemented?

A) Single prompt per batch: send multiple transaction descriptions together and ask the model to return one category per transaction in a single response (fewer round-trips, but needs reliable structured-output parsing and a fallback if the model's batch answer is malformed)

B) Concurrent individual calls: keep today's one-transaction-per-prompt format, but fire several calls at once instead of one at a time (simpler, same parsing as today, still cuts wall-clock time)

C) Sequential, same as today (no real batching) — just switching the model

D) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 5
For the price-range bucket added to the embedded text — fixed buckets (as you illustrated: $0–1, $1–5, $6–10, ...) or configurable? And should already-embedded transactions/recurring payments be **re-embedded** so the whole vector store stays consistent, or left as-is (old vectors have no price signal, new/changed ones do)?

A) Fixed buckets as illustrated; re-embed all existing rows so the vector store is fully consistent

B) Fixed buckets as illustrated; leave existing embedded rows alone (accept some inconsistency; only newly-embedded rows get the price signal)

C) Configurable bucket boundaries (env-tunable), and re-embed existing rows

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 6
How much should `embedding_similarity_threshold` (currently 0.75) increase?

A) A modest bump (e.g. 0.75 → 0.80)

B) A larger bump (e.g. 0.75 → 0.85)

C) Let the implementation pick a reasonable default and document the reasoning

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 7
"Somehow use the information from during ingestion" during matching — how should the LLM-predicted category be used when deciding whether to accept an embedding-similarity match?

A) Hard filter — an embedding match is only accepted if the new transaction's LLM-predicted category matches the candidate transaction's actual category (extra guard against false-positive matches)

B) Soft signal — factor agreement into the match score (e.g. a small score boost when categories agree) rather than rejecting disagreements outright

C) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 8
Should these refinements (price-bucket embedding, raised threshold, LLM-signal-assisted matching) apply to:

A) Transaction categorization matching only (`find_similar_transaction_via_embedding`, `recategorize_unsure_from_precedent`)

B) Both transaction categorization AND recurring-payment matching/detection (all embedding-based matching paths in the system)

C) Other (please describe after [Answer]: tag below)

[Answer]: B
