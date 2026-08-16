# Functional Design Plan — Frontend SPA Unit — Recurring Payments (Epic 8)

**Unit**: Frontend SPA (Unit 4). **Scope**: a 4th Dashboard tab ("Recurring Payments", FR-4) plus a nav badge on the Dashboard link (US-8.7, same pattern as `PendingReviewBadge`).

## No blocking questions

Panel location (Dashboard tab, not a separate page) and badge placement (Dashboard nav link) were already resolved in Requirements/Application Design. Component granularity follows the existing convention directly: one Frontend SPA component, no new page.

## Execution Checklist

- [ ] Add a **Recurring Payments** tab section to `frontend-components.md` (Addendum style)
- [ ] Add badge-placement reasoning to `business-logic-model.md` (mirrors `PendingReviewBadge`'s "hide entirely at zero" precedent, counting `overdueCount + pendingMatchCount + newSuggestionCount`, not `dueSoonCount`)

## Design (for Code Generation)

- **Status summary strip**: 4 small counts (due soon / overdue / pending review / new suggestions) at the top of the tab.
- **Payments list**: name, amount, frequency/due date, status badge (color per state), monthly set-aside for annual payments, category. Add-one-at-a-time form (US-8.1) and a bulk-import textarea accepting pasted rows (US-8.2).
- **Pending matches**: a compact table with Approve/Reject per row (US-8.4), same interaction shape as `ReviewPage`'s `ProposalTable`.
- **Detection suggestions**: a compact list with Add/Dismiss per row (US-8.6).
- **Nav badge**: on the "Dashboard" link, visible only when `overdueCount + pendingMatchCount + newSuggestionCount > 0`.
