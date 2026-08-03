# Functional Design Plan — Unit 3: Ingestion Worker Service

**Input**: `unit-of-work.md` (Unit 3 definition), `unit-of-work-story-map.md`, `application-design/components.md` + `component-methods.md` (Ingestion Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion), `database/functional-design/`

## Unit Context

Unit 3 owns 6 components and implements: US-1.1, US-1.2 (execution half), US-1.3, US-1.4, US-2.1–2.3, US-3.4 (retro job half), US-3.7 (conversion computation half), US-4.6 (conversion computation half), US-5.3 (secrets half). This is the most technically complex unit — it's where the genuinely hard problems (layout-adaptive extraction, OCR, categorization, FX) live.

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below + follow-up clarifications — Gemini (extraction) + OpenRouter (categorization fallback), no cross-provider retry, rapidfuzz similarity, structural+confidence extraction failure, statement-printed SGD priority + exchangerate.host fallback, 5s polling
- [x] Step 2: Generate `business-logic-model.md` — full pipeline for all 6 components
- [x] Step 3: Generate `business-rules.md` — 8 rules (WR-1..WR-8)
- [x] Step 4: Generate `domain-entities.md` — 5 internal DTO shapes
- [x] Step 5: Cross-check every story assigned to Unit 3 is covered — US-1.1, 1.2(execution half), 1.3, 1.4, 2.1-2.3, 3.4(retro half), 3.7(conversion half), 4.6(conversion half), 5.3(secrets half) all addressed; no gaps

## Clarifying Questions

### Question 1 — LLM Provider
Requirements Analysis floated "Claude API" as an example for the categorization LLM fallback. Confirming now, since it also affects the extraction pipeline (Question 2):

A) **Anthropic Claude API** (e.g., a Claude model with vision/PDF support) — used for both layout-adaptive statement extraction and categorization fallback

B) **OpenAI API** — GPT-family model for the same two purposes

X) Other (please describe after [Answer]: tag below)

[Answer]: X. Prioritise on free API calls from Openrouter or a $10/month GEMINI API key that i possess..

### Question 2 — OCR / Extraction Approach
Statement extraction needs to handle both text-based and scanned/image PDFs (FR-2.1). Modern LLMs from the provider chosen in Question 1 can often read PDF pages directly (including scanned ones, via vision) and extract structured data in one step, rather than running a separate OCR pass first.

A) **LLM-native document understanding** — send PDF pages (as images) directly to the vision-capable LLM, asking it to both "read" the page and extract structured transaction data in one call. Simpler pipeline (no separate OCR library/dependency), but ties extraction quality entirely to the LLM's document-vision capability and costs more tokens per statement.

B) **Traditional OCR + text LLM** — use a dedicated OCR library (e.g., Tesseract via `pytesseract`) to convert scanned pages to text first, then feed the combined text (native + OCR'd) to a text-only LLM call for structured extraction. More moving parts (an OCR dependency), but decouples "reading the page" from "understanding the transactions" and is cheaper per call.

X) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 3 — Similarity-Matching Algorithm
FR-5.2's first step needs a concrete "how similar is this new description to a past one" method.

A) **Fuzzy string similarity** (e.g., token-sort/token-set ratio via `rapidfuzz`) — fast, no external calls, works well for near-identical merchant strings (e.g., "NTUC FAIRPRICE #123" vs "NTUC FAIRPRICE #456"), but doesn't understand semantic similarity between differently-worded descriptions for the same merchant/purpose

B) **Embedding-based semantic similarity** (e.g., a local sentence-embedding model, cosine similarity against stored embeddings) — better at catching semantically-similar-but-differently-worded descriptions, but adds a model dependency and per-transaction embedding computation/storage

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 4 — Extraction Failure / Low-Confidence Criteria
Per FR-2.5, when should a statement be flagged as failed/needs-review rather than committed?

A) **Structural validation only** — flag as failed if the LLM's response doesn't parse as valid structured output (schema validation failure), or if zero transactions are extracted from a non-empty statement; otherwise trust whatever the LLM returns

B) **Structural validation + LLM self-reported confidence** — additionally ask the LLM to report a confidence level per statement (or per transaction), and flag as failed/needs-review if confidence is below a threshold, even if the output structurally parsed fine

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 5 — FX Rate API Provider
FR-10.3 needs a specific free/public historical exchange-rate API.

A) **Frankfurter** (frankfurter.app) — free, no API key required, ECB-sourced daily rates, straightforward REST API

B) **exchangerate.host** — free tier, no API key required for basic historical lookups

X) Other (please describe after [Answer]: tag below)

[Answer]:X. Most of the times, the statement would also have the converted to SGD amount.

### Question 6 — Worker Polling Interval
How frequently should the Ingestion Orchestrator poll the database for queued runs/jobs?

A) **Every 5 seconds** — near-instant pickup, negligible DB load at this scale

B) **Every 30 seconds** — even lower overhead, at the cost of up to 30s delay before a triggered run actually starts

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
