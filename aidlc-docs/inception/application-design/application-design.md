# Application Design — Bank Transaction Insights App (Consolidated)

This document consolidates `components.md`, `component-methods.md`, `services.md`, and `component-dependency.md`. See those files for full detail; this is the executive summary.

## Architecture Decisions (from application-design-plan.md)

| Decision | Choice |
|---|---|
| Architectural style | Separate services: **API Service** + **Ingestion Worker Service**, sharing one database |
| Ingestion execution model | Async background job; API Service enqueues, Worker polls/claims, both read/write a shared run/job DB table for status (no message broker needed) |
| Categorization engine | Pluggable `CategorizationStrategy` interface (Similarity Matcher, LLM Classifier) inside the Worker Service |
| Frontend/backend API style | REST (JSON over HTTP) |

## Services

1. **Frontend SPA** — the only UI surface; talks to API Service only
2. **API Service** — Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration, **Recategorization Review** *(added 2026-08-02)*
3. **Ingestion Worker Service** — Ingestion Orchestrator, Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, Currency Conversion
4. **Shared Database** — the only integration point between API Service and Worker Service (data contract, not code contract)

## Key Design Consequence Flagged During Design

Manual category correction (US-3.4) is handled entirely in the API Service, but the retroactive re-categorization of existing `UNSURE` transactions (FR-5.4) requires the Categorization Engine, which lives in the Worker Service. This is implemented as another async job (consistent with the ingestion-run pattern), not a direct synchronous call — keeping the two services fully decoupled. This means a manual correction's ripple effect on other `UNSURE` transactions completes shortly after the correction, not instantaneously — acceptable per the approved acceptance criteria, which do not require synchronous completion.

**Addendum (2026-08-02, Recategorization Review Panel — Epic 6)**: That same async job (FR-5.4) is now broadened to search already-categorized transactions too, and split by confidence: very-high-confidence `UNSURE` matches still auto-apply as before; everything else — lower-confidence `UNSURE` matches, and *every* match against an already-categorized transaction regardless of score — now creates a pending proposal instead of writing to `transactions`. Reviewing those proposals (approve/reject, individually or in bulk) is a **new, separate, synchronous** path in a new API Service component (Recategorization Review), analogous to `correctCategory()` itself rather than routed through the async job queue — a human clicking "approve" is a request/response action, not background work. See `recategorization-review-application-design-plan.md` for the full reasoning behind each of these calls.

## Story Traceability Validation (Step 10)

All 24 approved stories map to at least one component:

| Story | Component(s) |
|---|---|
| US-1.1 | Drive Connector |
| US-1.2 | Ingestion Trigger & Status, Ingestion Orchestrator |
| US-1.3 | Statement Extraction |
| US-1.4 | Duplicate Detection |
| US-1.5 | Ingestion Trigger & Status |
| US-2.1 | Categorization Engine (Similarity Matcher) |
| US-2.2 | Categorization Engine (LLM Classifier) |
| US-2.3 | Categorization Engine (fallback chain) |
| US-3.1 | Transaction Management |
| US-3.2 | Transaction Management |
| US-3.3 | Transaction Management |
| US-3.4 | Transaction Management, Categorization Engine (retro job) |
| US-3.5 | Transaction Management |
| US-3.6 | Transaction Management |
| US-3.7 | Transaction Management, Currency Conversion |
| US-4.1 | Dashboard/Insights |
| US-4.2 | Dashboard/Insights |
| US-4.3 | Dashboard/Insights |
| US-4.4 | Dashboard/Insights |
| US-4.5 | Dashboard/Insights, Transaction Management (drill-down target) |
| US-4.6 | Dashboard/Insights, Currency Conversion |
| US-5.1 | Auth |
| US-5.2 | Configuration |
| US-5.3 | (Environment-based, no runtime component — see components.md note) |

**Result (original 24 stories)**: Complete — no gaps. Every story has at least one owning component; no component exists without a story justifying it (no speculative/unused components).

### Addendum (2026-08-02): Epic 6 — Recategorization Review Panel

| Story | Component(s) |
|---|---|
| US-6.1 | Categorization Engine (broadened search) |
| US-6.2 | Categorization Engine (auto-apply path) |
| US-6.3 | Categorization Engine (always-review rule for already-categorized candidates) |
| US-6.4 | Recategorization Review, Frontend SPA (Review page) |
| US-6.5 | Recategorization Review |
| US-6.6 | Recategorization Review, Frontend SPA (nav badge) |

**Result (Epic 6)**: Complete — no gaps, no new speculative components. All 6 stories map to either the extended Categorization Engine or the new Recategorization Review component.
