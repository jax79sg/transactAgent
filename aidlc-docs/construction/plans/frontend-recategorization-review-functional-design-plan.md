# Functional Design Plan — Frontend SPA Unit — Recategorization Review Panel

**Unit**: Frontend SPA (Unit 4). **Scope**: new `/review` page, nav badge — no changes to existing pages.

## No blocking questions

Read `App.tsx`, `NavBar.tsx`, `IngestionPage.tsx`, `client.ts`, and `types.ts` directly before designing, to reuse this project's existing patterns (React Query polling/invalidation, URL-agnostic page-local state, the `ExportCsvButton` "acts on current view" precedent) rather than invent new ones. The page name ("Review") and terminology ("proposals") were already settled at the User Stories stage.

## Execution Checklist

- [x] Add `ReviewPage`/`ProposalTable`/`ProposalRow`/`BulkActionBar` and `NavBar`'s `PendingReviewBadge` to `frontend-components.md`'s component hierarchy and detail sections
- [x] Add "Pending Review Badge Polling" (30s interval, reasoning vs. the existing 3s ingestion poll) and "Review Selection State" (current-page-only `Set`, reset on page/list change) to `business-logic-model.md`
