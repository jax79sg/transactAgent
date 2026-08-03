# NFR Requirements Plan — Unit 3: Ingestion Worker Service

**Input**: `aidlc-docs/construction/ingestion-worker/functional-design/` (approved)

## Gap Caught While Preparing This Plan

Functional Design's Drive Connector section says "on first use, complete interactive OAuth" but doesn't specify *how*, given Unit 3 is a background worker with no browser-facing HTTP interface of its own (unlike Unit 2). This needs resolving now, since it's a genuine architecture decision with real implications for already-built Unit 2 — see Question 1 below.

## NFR Category Assessment

| Category | Assessment |
|---|---|
| Scalability | N/A — single personal user, one worker process |
| Performance | No hard target; LLM API latency (seconds per statement) is the dominant cost and is inherent to the chosen approach, not something to further optimize for a personal, manually-triggered workflow |
| Availability | N/A — Resiliency Baseline extension opted out |
| Security | API keys (Gemini, OpenRouter, Google OAuth client) via env vars (NFR-4.1); Drive refresh token storage approach is part of Question 1 |
| Tech Stack Selection | **Real decisions**: OAuth connection mechanism (Question 1), PDF-to-image library (Question 2). Google/OpenRouter SDKs, similarity/confidence threshold defaults, and the PBT framework are decided directly below (documented rationale, no user tradeoff). |
| Reliability | WR-1/WR-7 (no cross-provider retry, fail terminal) already captured in Functional Design |
| Maintainability | **PBT framework**: Hypothesis (Python's standard PBT library, matches `property-based-testing.md`'s own recommendation table) — decided directly. Applies to this unit's genuinely pure functions: the similarity-matching function, the currency-conversion source-priority resolver, and extraction-response schema validation (round-trip: raw LLM JSON -> validated `RawExtractedStatement` -> back), per Partial PBT mode (requirements.md NFR-5.2). |
| Usability | N/A — no UI in this unit |

## Direct Decisions (no user tradeoff, documented for transparency)

- **Google Drive SDK**: `google-api-python-client` + `google-auth-oauthlib` (official Google libraries)
- **Gemini SDK**: `google-genai` (official, current Google GenAI SDK)
- **OpenRouter client**: `openai` Python package pointed at OpenRouter's OpenAI-compatible `base_url` (OpenRouter's documented integration method — no separate SDK needed)
- **Similarity threshold**: default 85/100 (rapidfuzz `token_sort_ratio`), overridable via `SIMILARITY_THRESHOLD` env var — a starting point to tune based on real results, not a fixed architectural constant
- **Extraction confidence threshold**: default "medium" (statement-level), overridable via `EXTRACTION_CONFIDENCE_THRESHOLD` env var
- **PBT framework**: Hypothesis

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (OAuth connection mechanism, PDF-to-image library) — standard web OAuth via Unit 2 (interpreted from free-text answer), pdf2image
- [x] Step 2: Generate `nfr-requirements.md`
- [x] Step 3: Generate `tech-stack-decisions.md`

## Clarifying Questions

### Question 1 — Google OAuth Connection Mechanism
Since this unit has no browser-facing HTTP interface, how should the one-time interactive Google OAuth consent (US-1.1) actually happen?

A) **Via Unit 2's API**: add 2 new endpoints to the already-built Unit 2 (OAuth initiation + callback), storing the resulting refresh token in a new shared DB table that Unit 3 reads from. Requires retroactively modifying Unit 2 and adding a new Unit 1 migration, but keeps the whole flow inside the web app (Frontend could link to it).

B) **Standalone one-time CLI script bundled with Unit 3**: a small script you run manually once (e.g., `docker-compose run ingestion-worker python -m ingestion_worker.connect_drive`), which opens your browser, completes the OAuth flow via a local redirect URI, and writes the resulting refresh token into the same shared database directly. No changes needed to Unit 2 or its already-generated code.

C) **Pre-supplied token via `.env`**: you complete the OAuth flow yourself entirely outside this app (e.g., Google's OAuth Playground) and paste the resulting refresh token into `.env` — the app never runs an OAuth flow itself.

X) Other (please describe after [Answer]: tag below)

[Answer]: X. Is it possible to open a browser window and direct to Google login for login like what most web applications do?

### Question 2 — PDF-to-Image Library
Converting PDF pages to images (for Gemini's vision input, per Functional Design Question 2 = A) needs a library.

A) **`pypdfium2`** — pure-Python-installable (bundles PDFium, no system package dependency), fast, actively maintained

B) **`pdf2image`** — thin wrapper around the `poppler` system utility, requires installing `poppler-utils` in the Docker image separately, but is a very common/battle-tested choice

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
