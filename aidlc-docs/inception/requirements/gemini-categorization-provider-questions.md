# Gemini Categorization Provider Option — Requirements Clarification Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match your needs, choose the last option (Other) and describe your preference. Let me know when you're done.

**Context investigated before drafting these**: Statement extraction (`ingestion-worker/src/ingestion_worker/extraction/service.py`) already calls Gemini exclusively (`clients/gemini_client.py`) — there is no local alternative for extraction today. The transaction-categorization step (`categorization/llm_classifier.py` → `clients/openrouter_client.py`) uses an OpenAI-compatible endpoint (`openrouter_base_url`), which `config.py`'s own comment says was pointed at "a locally-hosted omlx-server instance" after hitting OpenRouter's free-tier rate limits — this is what "local omlx" means in this codebase. A similar local-server option exists for embeddings (`embedding_base_url`, used for recategorization similarity matching). `openrouter_base_url`, `openrouter_model`, and `gemini_model` are all already editable via the existing Settings page (`api-service/src/api_service/app_settings/catalog.py`).

There is also an unrelated, already in-flight post-completion change ("Account Balance at a Point in Time") whose Requirements Analysis is gated awaiting your answers in `aidlc-docs/inception/requirements/account-balance-questions.md`, created 2026-09-14 and still unanswered.

## Question 1
There's a prior post-completion change ("Account Balance at a Point in Time") already waiting on your answers in a separate question file. How would you like to sequence this new request against it?

A) Pause this new request — I'll go answer `account-balance-questions.md` first, then come back to this one

B) Set Account Balance aside for now — proceed with Requirements Analysis on this Gemini/local-oMLX provider feature first; Account Balance stays gated until I return to it

C) Answer both question files now, in whichever order — proceed with Requirements Analysis on each independently as answers come in

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 2
Which pipeline step(s) should get a Gemini-vs-local-oMLX provider choice? (Statement extraction itself is already Gemini-only with no local alternative today, so it's not a candidate for this toggle unless you want that to change too — see "Other" if so.)

A) Categorization only — the LLM step that classifies each transaction description into a category, currently always going to whatever `openrouter_base_url` points at

B) Embedding/semantic-matching only — the step used for recategorization similarity, currently always going to whatever `embedding_base_url` points at

C) Both categorization and embedding

D) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 3
How should the provider choice be exposed?

A) A new explicit "provider" toggle (e.g. Local / Gemini) on the existing Settings page for the in-scope step(s) from Q2 — when set to Gemini, reuse the existing `gemini_api_key` (and the model from Q4); when set to Local, use the existing `openrouter_base_url`/`openrouter_model` (or `embedding_base_url`/`embedding_model`) exactly as today

B) No new setting or code — just document that pointing `openrouter_base_url` at Gemini's own OpenAI-compatible endpoint already works today with the existing fields

C) A fully separate, independent set of Gemini-specific settings for the in-scope step(s) (its own model field), not reusing the extraction ones at all

D) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 4
When Gemini is selected for categorization (assuming Q2 includes categorization), which model should it use by default?

A) Reuse the existing `gemini_model` setting — the same model already used for statement-image extraction and the Ask AI feature

B) A new, separate setting for the categorization-specific Gemini model — text classification is a much lighter task than vision extraction and may warrant a different (e.g. cheaper/faster) model

C) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 5
Today, when the categorization LLM call fails after exhausting retries, the transaction is simply marked UNSURE — there's a deliberate "no cross-provider fallback" rule (WR-7) already in place. If Gemini is selected as the provider and it fails (rate limit, network error, etc.), what should happen?

A) Same rule as today: exhausted retries → that transaction is marked UNSURE, no automatic fallback to the other provider

B) Automatically fall back to the local oMLX endpoint (if one is configured) before giving up on that transaction

C) Other (please describe after [Answer]: tag below)

[Answer]:

## Question 6
Every existing Settings-page field (all 44 of them) is one global, deployment-wide value. Should the provider choice work the same way?

A) Yes — one global setting for the whole deployment, same as every other Settings-page field, applying to all ingestion runs until changed

B) No — configurable per-ingestion-run (e.g. chosen at statement-upload time)

C) Other (please describe after [Answer]: tag below)

[Answer]:
