# Business Logic Model — Unit 4: Frontend SPA

Client-side logic beyond simple "call an endpoint and render the response."

## Session Lifecycle (AuthProvider)

- **On app load**: read token from `sessionStorage`; if present and not obviously expired (compare `expiresAt` to now), treat as logged in optimistically — the next API call will `401` if it's actually invalid, at which point the session is cleared.
- **Sliding expiry** (Unit 2 NFR Requirements Question 2 = A): every successful authenticated API response may carry a refreshed token (exact transport — response header vs. body field — finalized in Code Generation matching Unit 2's actual implementation); if present, the frontend updates its stored token so continuous use never logs the user out.
- **On 401 from any API call**: clear session state and `sessionStorage`, redirect to `/login`. Centralized in a single API-client wrapper (an interceptor/fetch-wrapper) so this logic exists once, not duplicated per API call site.

## Ingestion Run Polling Lifecycle

- **Trigger**: `POST /ingestion/runs` -> on success (`202`), immediately start polling `GET /ingestion/runs/{runId}` every 3 seconds.
- **Poll loop termination**: stops as soon as `status` is `completed`, `completed_with_failures`, or `failed` — never polls indefinitely.
- **Page navigation during a run**: if the user navigates away from `/ingestion` while a run is active and comes back, `ActiveRunProgress` re-derives "is a run active" from `GET /ingestion/runs` (most recent entry) rather than relying on in-memory state that would've been lost — so an in-progress run is never "forgotten" by the UI.
- **409 on trigger**: rather than treating this as a hard error, the frontend uses the `existingRunId` in the response body to immediately start polling that run instead — the user's click still results in seeing live progress, just for the already-running run.

## Filter/Group State <-> URL Mapping

- All `TransactionsPage` filter/group/sort/page state is serialized to the URL query string (e.g., `/transactions?category=Groceries&dateFrom=2026-01-01`) and deserialized from it on page load — this makes filtered views bookmarkable/shareable and is what makes dashboard drill-down (below) work via simple navigation rather than passing state through application memory.
- Changing any filter control updates the URL (without a full page reload) and triggers a new `GET /transactions` call with the updated query params.

## Dashboard Drill-Down (US-4.5)

- Clicking a chart segment (a specific category+month, or bank+month) constructs a `/transactions` URL with `category`/`bank` and a `dateFrom`/`dateTo` pair spanning that segment's month, then navigates there — reusing the same URL-driven filter state described above rather than a separate drill-down-specific code path.

## CSV Export

- Reuses the exact current `TransactionFilterBar` state (minus pagination) to construct the `GET /transactions/export.csv` request — guaranteeing "what you see is what you export" (US-3.6).

## Category Whitelist Cache

- The active-category list (used to populate every category `<select>` across the app — correction dropdown, add/rename forms) is fetched once per session and cached client-side, invalidated (refetched) after any add/rename/remove action on `SettingsPage` — avoiding a redundant `GET /categories` call before every single inline correction.

## Pending Review Badge Polling (added 2026-08-02 — Epic 6)

- `PendingReviewBadge` polls `GET /recategorization/proposals/pending-count` every 30 seconds, regardless of which page is active (mounted once at `NavBar`, not per-page) — deliberately much looser than the Ingestion 3-second poll: that poll is watching one specific run the user just triggered and is actively waiting on, while this is an ambient "is there anything waiting" indicator nobody is staring at in real time. 30s keeps the badge reasonably fresh without adding meaningful load for a single-user app.
- Any successful approve/reject/bulk-approve/bulk-reject action on `ReviewPage` immediately invalidates the pending-count query (React Query cache invalidation) rather than waiting for the next 30s tick — so the badge updates instantly for actions the user just took, and only relies on polling to catch changes from elsewhere (e.g. a new correction generating fresh auto-applied/pending proposals via the next ingestion-worker poll cycle).

## Backup Status Panel Polling (added 2026-08-08 — Epic 7)

- `BackupStatusPanel` polls `GET /backups/status` every 5 minutes, mounted only on `ReviewPage` (unlike `PendingReviewBadge`, this isn't shown in the nav, so it only needs to be fresh while that page is open). Looser than `PendingReviewBadge`'s 30s deliberately: a backup outcome changes at most once a night (WR-11/BR-17 — at most one `BackupRun` row per day), so sub-minute freshness has no value here, unlike the pending-proposal count which can change every few seconds as ingestion runs land.
- No cache-invalidation trigger exists for this query (unlike the pending-count badge, which invalidates on approve/reject) — nothing on the Frontend ever writes a `BackupRun` row, so there's no local action that could make the cached status stale ahead of the next poll.

## Review Selection State (added 2026-08-02 — Epic 6)

- `ReviewPage` holds a `Set<proposalId>` of the current page's selected rows, reset whenever the page number or the underlying proposal list changes (e.g. after a bulk action removes resolved rows) — never carried across pages, consistent with `BulkActionBar`'s "acts on the current page" scope (frontend-components.md).
- "Select all" toggles every row on the current page in one action; unchecking any individual row after "select all" simply removes it from the `Set`, it does not need a separate "partial selection" mode.
