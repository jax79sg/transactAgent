# Functional Design Plan — Frontend SPA Unit — Nightly Transaction Backup

**Unit**: Frontend SPA (Unit 4). **Scope**: a new **BackupStatusPanel** on the existing Review page, visually separate from `ProposalTable` (per the requirements clarification), consuming `GET /backups/status`.

## No blocking questions

Every product decision was already resolved during Requirements clarification (panel location: Review page, separate panel; failure messaging: Drive-reconnect prompt vs. generic indicator). Component granularity follows the existing Epic 6 precedent directly: one new component on the existing single-Frontend-SPA-component convention, not a new page.

## Execution Checklist

- [ ] Add a **BackupStatusPanel** section to `frontend-components.md` (Addendum style, matching the existing `ReviewPage / ProposalTable / ProposalRow / BulkActionBar` and `NavBar / PendingReviewBadge` sections)
- [ ] Add polling-interval reasoning to `business-logic-model.md`, matching `PendingReviewBadge`'s existing precedent for choosing a deliberately loose interval for an ambient, not-actively-watched indicator (a nightly backup changes at most once a day, so an even looser interval than the 30s pending-count badge is justified)
