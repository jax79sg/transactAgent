# Code Generation Plan — Frontend SPA Unit — Recategorization Review Panel

**Unit**: Frontend SPA (Unit 4). **Stories**: US-6.4, US-6.5, US-6.6.
**Dependencies**: API Service unit (complete).

## Steps

1. [x] **Frontend Components Generation**:
   - Created: `frontend/src/api/recategorization.ts` (6 client functions matching the 6 new endpoints)
   - Modified: `frontend/src/api/types.ts` — `ProposalDTO`, `ProposalPage`, `PendingCountResponse`, `BulkApproveResponse`, `BulkRejectResponse`
   - Created: `frontend/src/pages/ReviewPage.tsx` — proposal table, per-row approve/reject, select-all + bulk actions, partial-bulk-failure inline notices, pagination
   - Modified: `frontend/src/components/NavBar.tsx` — `PendingReviewBadge` (30s poll, matching business-logic-model.md), new "Review" nav link
   - Modified: `frontend/src/App.tsx` — `/review` route
2. [x] **Frontend Components Unit Testing**:
   - Created: `frontend/tests/ReviewPage.test.tsx` (8 tests)
   - Created: `frontend/tests/NavBar.test.tsx` (3 tests)
3. [x] **Documentation Generation**:
   - Modified: `aidlc-docs/construction/frontend/code/README.md`

## Verification

- [x] Ran the two new test files in isolation: 11/11 passing (after fixing one real assertion bug — TanStack Query v5 calls `mutationFn(variables, context)` with a second internal-context argument the tests hadn't accounted for)
- [x] Ran the full frontend test suite: 47/47 passing, no regressions
- [x] Ran `npm run build` (`tsc -b && vite build`): clean type-check, clean production build
