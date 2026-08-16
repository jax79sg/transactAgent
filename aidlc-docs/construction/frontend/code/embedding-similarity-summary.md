# Transaction Embedding Badge — Code Summary (Epic 9)

No new files — the smallest of this feature's 3 frontend-touching changes so far.

| File | Change |
|---|---|
| `api/types.ts` | `TransactionDTO` +`embeddingStatus: "pending" \| "completed"` |
| `pages/TransactionsPage.tsx` | New `EmbeddingStatusBadge` component (a quiet dot, `title` tooltip, `data-testid="embedding-status-badge"`), rendered inline in `TransactionRow`'s Description cell |

## Key decisions

- **Inline, not a new column**: avoids touching `GroupHeaderRow`'s `colSpan={8}` or the loading-row colspan — the badge lives inside the existing Description `<td>`.
- **No polling, no cache invalidation hook**: unlike every other badge in this app (`PendingReviewBadge`, `BackupStatusPanel`, `RecurringPaymentsBadge`), this one has no interval timer and nothing invalidates its query on a user action — it simply reflects whatever `GET /transactions` last returned, because nothing in this unit ever *writes* `embeddingStatus` (FR-6's async/eventually-consistent framing already covers the staleness).
- **Deliberately quiet styling** (a small `bg-slate-300`/`bg-emerald-400` dot, not a colored banner or count) — FR-7 is explicit this is a processing-status indicator, not a claim about match quality or precedent found, so it shouldn't visually compete with the app's actionable attention badges.

## Real thing caught before running tests

`TransactionDTO` is now a required field across the whole frontend, not just the API — five test files construct `TransactionDTO`-shaped mock objects directly (`groupKeyFor.test.ts`, `askAiLinkFor.test.ts`, `DashboardPage.test.tsx`, `ReviewPage.test.tsx`, `TransactionsPage.test.tsx`, one construction site each). Grepped for every `conversionUnavailable:` occurrence (a reliable anchor — every mock transaction object sets it) to find all five before running anything, rather than discovering them one at a time via `tsc -b` failures. `npx tsc -b` confirmed clean on the first run after all five were updated together.

## Tests

- `tests/TransactionsPage.test.tsx`: `pageOf()` helper extended with an `embeddingStatus` override parameter; +2 tests (pending-state tooltip, completed-state tooltip)

Full suite: **83/83 passing** (up from 81). Clean `tsc -b` + `vite build`.
