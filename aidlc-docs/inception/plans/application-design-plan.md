# Application Design Plan — Bank Transaction Insights App

**Input**: `aidlc-docs/inception/requirements/requirements.md` (approved), `aidlc-docs/inception/user-stories/stories.md` (approved, 5 epics / 24 stories)

## Design Scope

Five epics translate into these candidate functional areas:
1. **Auth** — login/session (US-5.1)
2. **Drive Ingestion** — OAuth connection, folder scan, duplicate detection, run orchestration/history (US-1.1, 1.2, 1.4, 1.5)
3. **Statement Extraction** — OCR + layout-adaptive parsing, bank/currency identification (US-1.3)
4. **Categorization** — similarity matching, LLM fallback, UNSURE handling, retroactive re-categorization on manual correction (US-2.1–2.3, US-3.4 edge case)
5. **Transaction Management** — CRUD, filter/group/sort, manual correction, CSV export (US-3.1–3.7)
6. **Currency Conversion** — FX rate fetch/cache, historical lookup, fallback (US-3.7, US-4.6, FR-10)
7. **Dashboards/Insights** — aggregation and trend queries (US-4.1–4.6)
8. **Configuration** — category whitelist management, secrets (US-5.2, US-5.3)

## Execution Checklist

- [x] Step 1: Confirm architectural style (modular monolith vs. separate services) — Answer: B, separate services
- [x] Step 2: Confirm ingestion execution/orchestration model (sync vs. async job) — Answer: A, async background job
- [x] Step 3: Confirm categorization engine coupling/extensibility — Answer: A, pluggable
- [x] Step 4: Confirm frontend/backend boundary and communication style — Answer: A, REST
- [x] Step 5: Generate `components.md` — component definitions and responsibilities for the 8 functional areas above (plus Frontend as a top-level component)
- [x] Step 6: Generate `component-methods.md` — method signatures per component (high-level; detailed business rules deferred to Functional Design)
- [x] Step 7: Generate `services.md` — orchestration services and how they coordinate components (e.g., an Ingestion Orchestration service coordinating Extraction → Categorization → Currency Conversion → Transaction persistence)
- [x] Step 8: Generate `component-dependency.md` — dependency matrix, communication patterns, data flow diagram
- [x] Step 9: Generate consolidated `application-design.md`
- [x] Step 10: Validate design completeness against all 24 stories (every story maps to at least one component/method) — complete, no gaps

## Clarifying Questions

### Question 1 — Architectural Style
Given this is a single-user, docker-compose-deployed app, how should the backend be structured?

A) **Modular monolith** — one backend service/container, internally organized into clear modules (auth, ingestion, extraction, categorization, transactions, currency, dashboards, config) communicating via in-process function calls. Simplest to build, deploy, and debug for a single-user app.

B) **Separate services** — split into multiple independently-deployed backend services (e.g., an "ingestion worker" service separate from the "API" service), communicating over HTTP/message queue. More operational complexity, but isolates the long-running ingestion pipeline from the request/response API.

X) Other (please describe after [Answer]: tag below)

[Answer]:B

### Question 2 — Ingestion Run Execution Model
An ingestion run involves scanning Drive, downloading PDFs, OCR, LLM calls, and DB writes — this could take anywhere from seconds to minutes depending on file count. How should the UI stay responsive during this (per US-1.2's "live/near-live progress")?

A) **Async background job**: triggering ingestion enqueues a background job immediately; the UI polls (or uses a websocket/SSE) for progress updates and can navigate away/return without losing progress state

B) **Synchronous blocking request**: triggering ingestion blocks the HTTP request until the whole run completes, with the UI showing a loading state for the full duration (simpler to build, but the UI is locked/unresponsive for the run's full duration and a lost connection loses progress visibility)

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3 — Categorization Engine Extensibility
Should the categorization engine (similarity search + LLM fallback) be designed as a swappable/pluggable component (e.g., so you could later swap the LLM provider or add a new matching strategy without touching other components), or is a direct, non-abstracted implementation fine given this is a personal project?

A) **Pluggable** — define a clear interface/contract for "categorization strategy" so the similarity matcher and LLM fallback are swappable implementations behind it

B) **Direct implementation** — no abstraction layer needed; implement the hybrid logic (FR-5.2) directly, optimizing for simplicity over future swappability

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 4 — Frontend/Backend Communication
How should the frontend (rich SPA) communicate with the backend?

A) **REST API** — conventional REST endpoints (e.g., `GET /transactions?category=...`), JSON over HTTP — simple, well-understood, easy to filter/paginate

B) **GraphQL API** — single flexible endpoint, client specifies exactly what data/fields it needs — more upfront setup, but very good fit for the varied filter/group/dashboard query shapes in this app

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done. I'll analyze answers for ambiguity before generating the design artifacts.
