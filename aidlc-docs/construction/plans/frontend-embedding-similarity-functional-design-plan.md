# Functional Design Plan — Frontend SPA Unit: Local Embedding-Based Semantic Similarity (Epic 9)

## Genuinely open item
None. Scope exactly as fixed at Application Design (`components.md`): a small, inline, per-row badge in the
existing transaction list — no new page, no new component, no polling/counting logic (unlike `NavBar`'s
attention badges), since FR-7 is explicit that this is a processing-status indicator only, not an
action-needed signal.

## Decisions
1. **Inline in the existing `TransactionRow`'s Description cell**, not a new table column — avoids touching
   `colSpan` on `GroupHeaderRow` (currently `colSpan={8}`, matching the fixed column count) and the loading
   row, keeping this change minimal (US-9.1's own "just a badge" framing).
2. **Two visual states only** (`pending`/`completed`, Database `BR-24`) — a small dot/icon with a `title`
   tooltip ("Embedding: pending" / "Embedding: computed"), not a colored banner or anything demanding
   attention — deliberately quiet, matching FR-7's "not a claim about match quality" framing.
3. **No polling** — the badge reflects whatever `GET /transactions` already returned; the existing
   TanStack Query cache/refetch behavior for the transaction list is unchanged, no new interval timer (unlike
   `NavBar`'s 5-minute-poll badges, which exist specifically to surface something actionable across page
   loads).

## Steps
- [ ] Addendum to `frontend-components.md`'s `TransactionsPage / TransactionFilterBar / TransactionTable /
  TransactionRow` section
- [ ] Addendum to `business-logic-model.md` (if warranted — this is close to purely presentational, so likely
  a short note rather than new logic)

## Mandatory Artifacts
- [x] `frontend-components.md` — updated in place
- [x] `business-logic-model.md` — updated in place (brief)
