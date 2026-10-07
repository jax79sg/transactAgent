# Requirements — Gemini as a Categorization Provider (2026-10-05)

**Request**: "What if instead of the qwen model for the categorization, I use the Gemini model that I used for extraction of statements?" → after an assessment, "Ok go ahead" to the recommended design.
**Depth**: Minimal — a single enumerated setting with one code path. **User Stories**: skipped (a configuration switch with no new user-facing flow). **Application / Functional Design, NFR stages**: skipped (no new component, entity or business rule; the design is the setting and one function).
**Why now**: the local categorisation model's files were removed from disk on 2026-10-02, which blocked the real Account Balance backfill; the user wants Gemini instead, and the local option is kept.

## Answers to the paused questions (`gemini-categorization-provider-questions.md`)
Q1 = A (set earlier). Q2–Q6 were proposed by the assistant and accepted by the user ("Ok go ahead."): **Q2 = A** categorisation only (embeddings are a separate decision); **Q3 = A** an explicit provider setting; **Q4 = A** reuse `gemini_model`; **Q5 = A** same rule as today (a failed call leaves the transaction UNSURE, no cross-provider fallback, WR-7); **Q6 = A** one global setting.

## Requirements
- **FR-GC-1** A Settings-page setting `categorization_provider` with values `local` (default) and `gemini`.
- **FR-GC-2** `local` behaves exactly as before: the OpenAI-compatible endpoint, key and model in `openrouter_base_url`, `OPENROUTER_API_KEY`, `openrouter_model`.
- **FR-GC-3** `gemini` sends the same categorisation requests (same prompt, temperature, batching, retry and UNSURE rules) to Google's OpenAI-compatible endpoint with the existing `GEMINI_API_KEY` and `gemini_model`; no second key to configure.
- **FR-GC-4** The setting is validated: the Settings page accepts only the two values, and the worker refuses to start on any other value rather than silently choosing a provider.
- **FR-GC-5** The Settings page says what `gemini` means for cost and privacy (each transaction's description and SGD amount is sent to Google), and that `openrouter_*` apply only to `local`.
- **NFR-GC-1** Takes effect when the worker restarts, like the other worker settings; the override file wins over the deployed value.
- **NFR-GC-2** No change to the extraction path, the embedding path, or any existing setting's behaviour.

## Evidence behind the choice (2026-10-05, read-only, the worker's own `classify_batch`)
On 160 of the user's manual corrections (ground truth) Gemini Flash-Lite scored 45.6% (OpenJev 24.4%); on 160 auto-labelled rows 71.9% agreement (65.6%); on the 598-description curated validation set 69.2% agreement against an always-Dining baseline of 41.1% (OpenJev 51.7%), with 85.6% agreement with the labels the earlier LLM assigned. 0.9 s per batch of 8, 16–26 descriptions per second (OpenJev 3–4); about 10 cents per full reingest at $0.30 / $2.50 per million input / output tokens. Qwen itself could not be measured (its files are gone), so "better than Qwen" is unproven; near parity is indicated.
