# Requirements Clarification Questions — Local Embedding-Based Semantic Similarity

Please answer by filling in the letter choice after each `[Answer]:` tag. If none of the options fit, choose
"Other" and describe. Let me know when you're done.

## Question 1
You mentioned loading `google/embeddinggemma-300m` on "olmx" — I want to confirm the exact runtime before
this becomes a locked-in tech-stack/infrastructure decision.

A) Ollama (runs as a local server process; the project would call its HTTP API, similar in shape to how OpenRouter is already called)

B) llama.cpp / GGUF-based runtime (embedded directly in the Ingestion Worker process, no separate server)

C) ONNX Runtime (embedded directly in the Ingestion Worker process, no separate server)

D) MLX (Apple Silicon–specific; would restrict where this can run, e.g. not portable to a typical Linux Docker host)

E) Other (please describe after [Answer]: tag below)

[Answer]: E. omlx

## Question 2
Where should the embeddings be stored (the "vector store")?

A) `pgvector` extension on the existing Postgres database — no new service, one new table/column, reuses the existing DB unit and its migration/backup story

B) A separate, dedicated vector database service (e.g. Qdrant, Chroma, Milvus) — new container in `docker-compose`, its own persistence/backup story

C) In-memory / rebuilt-on-startup index (no persistent vector storage — recomputed from `transactions` each time the worker starts)

D) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 3
The Categorization Engine currently has a fuzzy-text Similarity Matcher (`rapidfuzz`/`token_sort_ratio`,
WR-3, just extended by WR-20's reference-code-noise normalization). How should embedding-based similarity
relate to it?

A) **Replace** the existing fuzzy-text matcher entirely — embedding similarity becomes the only precedent-matching step (WR-20's regex normalization would then be dead code to remove)

B) **Run alongside, as an earlier/preferred step** — try embedding similarity first; if no candidate clears its threshold, fall back to the existing fuzzy-text matcher exactly as today

C) **Run alongside, as a fallback** — keep fuzzy-text matching as the primary step (unchanged); only consult embedding similarity if fuzzy-text matching finds nothing

D) **Independent, informational only for now** — embedding similarity powers only the new UI badge (Question 5) and is not used to make any categorization decision yet; categorization logic is completely unchanged in this iteration

E) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 4
Beyond categorization/recategorization (your point 3), the same fuzzy-text matcher is also reused by two
other existing features: Recurring Payment matching (WR-16, matching a transaction against a recurring
payment's name) and the recurring-payment Detection Scan (WR-19). Should this change touch those too?

A) Yes — apply the same embedding-based approach decided in Question 3 everywhere the fuzzy-text matcher is currently used

B) No — scope this strictly to categorization/recategorization only, per your point 3; Recurring Payments keeps using the existing fuzzy-text matcher unchanged

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 5
What should the transaction-list "badge" (your point 2) actually mean to the user?

A) "A semantically similar past transaction was found" — i.e. a precedent-found indicator, roughly analogous to today's implicit similarity-match success, now made visible

B) "This transaction's embedding has been computed and stored" — a pure processing-status indicator, no semantic claim about matches

C) "This transaction is a candidate the system is unsure about and a similar precedent might help you confirm its category" — an actionable hint tied to `UNSURE`-category transactions specifically

D) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 6
Embedding computation happens "upon ingestion... in batches and asynchronously if more efficient" (your
point 2). Should the badge be allowed to lag behind the transaction actually appearing in the list (an
eventually-consistent background job), or must it be ready by the time the statement-processing run is
marked complete?

A) Eventually consistent — a background/batched job computes embeddings after ingestion; the badge may appear moments-to-minutes after the transaction is first visible

B) Synchronous within the ingestion run — embeddings must be computed and stored before the run is marked `completed`, same guarantee as extraction/categorization today

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 7
What should happen if the local embedding runtime is unavailable or a call fails (analogous to WR-1/WR-7's
existing "no silent retry across providers" rule for the categorization LLM)?

A) The affected transaction(s) simply have no embedding (no badge) — statement ingestion and categorization proceed unaffected, exactly as if this feature didn't exist for that run

B) The whole statement is flagged `failed`, same severity as an extraction failure (WR-1) — embeddings become a hard requirement for a successful ingestion run

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 8
This project's existing similarity-related fixes (Epic 8's matcher reuse, WR-20) have all been forward-only
by explicit choice — no retroactive re-scan of historical transactions. Given embedding-based similarity is
only useful once there's history to compare against, should this feature include a one-time backfill of
embeddings for existing transactions?

A) Yes — a one-time backfill job computes embeddings for all existing transactions as part of this change, so precedent search has meaningful history from day one

B) No — stay forward-only per this project's established pattern; only newly-ingested transactions get embeddings, and the feature's usefulness grows naturally over time

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 9
Should WR-20's reference-code-noise regex normalization (just shipped) still run on description text
*before* it's fed to the embedder, or is that no longer needed?

A) Yes, still normalize first — keep it cheap and remove obviously-irrelevant noise (like a random reference number) before embedding, even though embeddings are more robust to noise than exact-text fuzzy matching

B) No — feed the raw description directly to the embedder; a semantic embedding model should already be robust to this kind of noise, and pre-stripping adds a maintenance burden for no real benefit

C) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 10
Should vector similarity introduce its own new configurable decision threshold(s) (separate from the
existing `similarity_threshold`=85.0 / `recategorization_auto_apply_threshold`=97.0, which are text-fuzzy-
score-specific and explicitly out of scope to change), or should it stay threshold-free for this iteration?

A) Yes — introduce new, separate cosine-similarity threshold(s), tuned during Code Generation/testing, analogous to how the existing thresholds work

B) No thresholds yet — this iteration only surfaces the nearest-neighbor result and its raw similarity score (e.g. for the badge/informational use in Question 5); no auto-apply or gating decision is made from it

C) Other (please describe after [Answer]: tag below)

[Answer]:A
