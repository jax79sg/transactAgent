# Requirements — Gemini as an Embedding Provider (2026-10-05)

**Request**: "lets do up the embedding, using this a suitable gemini model as well." (the follow-on to the categorisation provider, where embeddings were deliberately left out: Q2 = A).
**Depth**: Minimal — one provider setting and one model setting beside the existing categorisation one. **User Stories, Application / Functional Design, NFR stages**: skipped (no new user-facing flow, component or business rule). The choice of model and thresholds is data-driven, below.
**Why**: the local embedding model's files were removed from disk on 2026-10-02, so embeddings had been switched off (`embedding_base_url` empty) and matching fell back to fuzzy text only.

## Decisions (made by the assistant under the standing instruction; the user asked for "a suitable Gemini model")
- **Model: `gemini-embedding-2`** (generally available since 2026-05-20). Chosen over `gemini-embedding-001` because it returns L2-normalised vectors at reduced sizes (measured: norm 1.000 at 768; `-001` gave 0.593) and is the current model. It accepts the `dimensions` parameter and batches through Google's OpenAI-compatible endpoint (tested).
- **Size: 768** — the existing `embedding_dimensions`, so the Qdrant collection recreated by the backfill needs no change.
- **Task prefix: `task: classification | query: `** on both stored and query text, because on the user's labelled data it matched far more neighbours at the same precision than the raw text.
- **Thresholds for this model: `embedding_similarity_threshold` 0.94, `recategorization_auto_apply_threshold` 99** (the old 0.92 / 97 were calibrated for `embeddinggemma`; the original gate + 0.05 relationship is kept).
- **Key**: reuse `GEMINI_API_KEY` (as for categorisation). **Failure**: no retry, soft-fail to fuzzy-text matching, exactly as today (WR-25).

## Requirements
- **FR-GE-1** `embedding_provider` setting (`local` default | `gemini`) and `gemini_embedding_model` (default `gemini-embedding-2`).
- **FR-GE-2** `local` behaves exactly as before (endpoint, key, model; an empty endpoint means embeddings are off).
- **FR-GE-3** `gemini` calls Google's OpenAI-compatible endpoint with the existing key, asks for `embedding_dimensions`-sized vectors, prefixes the task, uses a bounded timeout and never retries.
- **FR-GE-4** A returned vector of the wrong size is treated as unavailable (it would be rejected by the vector store); the value of `embedding_provider` is validated at startup.
- **FR-GE-5** The Settings page says what `gemini` means for privacy and cost, that vectors from different models cannot be compared (so switching re-embeds), and the calibrated thresholds for each provider.
- **NFR-GE-1** No change to categorisation, extraction or any other setting's behaviour; the local path's request is byte-for-byte the same.

## Evidence (2026-10-05): the user's own 6,645 labelled transactions (pre-backfill snapshot; 44 categories), nearest neighbour among the others
"Different description" = the case where embeddings add value over exact matching. Cosine thresholds, precision / coverage:

| | raw text | with the classification prefix |
|---|---|---|
| ≥ 0.92 | 97.5% / 82.1% | 95.4% / 95.6% |
| ≥ 0.94 | 98.5% / 73.1% | 96.5% / 91.8% |
| ≥ 0.96 | 98.9% / 33.2% | 98.5% / 82.7% |
| ≥ 0.97 | 98.9% / 22.6% | 99.1% / 68.0% |
| ≥ 0.98 | 99.1% / 16.3% | 99.6% / 30.2% |
| ≥ 0.99 | 99.7% / 10.7% | 99.3% / 18.0% |

Context: fuzzy-text matching gets 97.4% precision at 47.6% coverage (score ≥ 85). At equal precision the prefixed embeddings cover far more (about 99% precision at 68% coverage against 23% for raw text). Labels that were themselves produced by similarity matching flatter every model, so read these as a comparison, not an absolute accuracy; on the transactions the user labelled by hand precision is lower (e.g. 93% at ≥ 0.96) but follows the same shape.
