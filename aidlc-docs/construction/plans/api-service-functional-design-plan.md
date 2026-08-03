# Functional Design Plan — Unit 2: API Service

**Input**: `aidlc-docs/inception/application-design/unit-of-work.md` (Unit 2 definition), `unit-of-work-story-map.md`, `application-design/components.md` + `component-methods.md` (Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration components), `database/functional-design/` (the schema this unit reads/writes — Unit 2 owns no new entities of its own)

## Unit Context

Unit 2 owns 5 components (Auth, Transaction Management, Dashboard/Insights, Ingestion Trigger & Status, Configuration) and implements or co-implements these stories: US-1.2 (trigger/status half), US-1.5, US-3.1–3.7, US-4.1–4.6, US-5.1, US-5.2, US-5.3 (env config half). It defines no new domain entities — it consumes Unit 1's schema — so this Functional Design focuses on business logic (query/filter/aggregation logic, the correction-then-enqueue workflow, auth session handling) and the request/response contract shape, not new entities.

## Execution Checklist

- [x] Step 1: Resolve clarifying questions below (session mechanism, session duration, pagination style, category-removal-blocked UX) — JWT, 24h sliding, offset/limit, count-only
- [x] Step 2: Generate `business-logic-model.md` — auth session lifecycle, transaction query/filter/group logic, manual-correction-then-job-enqueue workflow, dashboard aggregation logic (per insight type), CSV export logic, ingestion-trigger validation/enqueue logic, category CRUD logic
- [x] Step 3: Generate `business-rules.md` — 10 API-layer rules (AR-1..AR-10)
- [x] Step 4: Generate `domain-entities.md` — request/response DTOs for each endpoint (explicitly noting no new persisted entities; DTOs are transient shapes over Unit 1's schema)
- [x] Step 5: Cross-check every story assigned to Unit 2 in `unit-of-work-story-map.md` is covered — US-1.2(split)/1.5/3.1-3.7(splits noted)/4.1-4.6(split)/5.1/5.2/5.3(split) all addressed in business-logic-model.md; no gaps

## Clarifying Questions

### Question 1 — Session Mechanism
How should the single-user login session (US-5.1) be implemented?

A) **Stateless JWT** — signed token issued on login, sent as a Bearer header or cookie, validated without a DB lookup on every request. Simpler infra, but revoking a session before expiry (e.g., forced logout) isn't naturally possible.

B) **Server-side session** — a session record persisted in the database (a new lightweight `sessions` table, added by this unit) referenced by an opaque cookie value; every request does a DB lookup to validate. Slightly more DB load (negligible at this scale), but sessions can be explicitly revoked/logged-out server-side.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 2 — Session Duration
How long should a login session last before requiring re-authentication?

A) **Short-lived with sliding expiry** — e.g., 24 hours, refreshed on activity — balances security and convenience for a personal app checked periodically

B) **Long-lived** — e.g., 30 days or "until explicit logout" — you're the only user on your own machine, prioritize convenience over re-login friction

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3 — Transaction List Pagination
US-3.1's transaction table needs to page through potentially thousands of rows over time. What pagination style?

A) **Offset/limit** (`?page=2&pageSize=50`) — simplest to implement and reason about; fine for this data volume; standard fit for a UI with page-number controls

B) **Cursor-based** (`?after=<opaque-cursor>`) — more robust against data shifting under the user while paging (e.g., new ingestion completing mid-browse), but more complex to implement for comparatively little benefit at personal-app scale

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 4 — Category-Removal-Blocked UX
Per US-5.2's edge case, when you try to remove a category still in use, what should the API return?

A) **Reject with a count** — "Cannot remove: 12 transactions still use this category" (count only, no need to enumerate every transaction in the error response — the user can filter the transaction table by that category to find them)

B) **Reject with the full list of affected transaction IDs** in the response, so the UI could (in a future enhancement) offer a direct "reassign these" flow

X) Other (please describe after [Answer]: tag below)

[Answer]:A

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
