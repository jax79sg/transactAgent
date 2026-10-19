# Code Generation Plan — Frontend Unit — Probable Duplicate Statement Detection (Epic 14)

**This plan is the single source of truth for Frontend Code Generation of this feature.**

**Unit**: Frontend (Unit 4). **Stories**: US-14.1 to 14.6 (the visible side). **Design source**: `aidlc-docs/construction/frontend/functional-design/` (the Epic 14 sections) and the API design's pinned endpoint paths.
**Code location**: workspace root, `frontend/` (modified in place). Documentation: `aidlc-docs/construction/frontend/code/` (markdown only). One PR for Epics 13 and 14; nothing committed or pushed. Plan and gate passed under the user's standing instruction of 2026-10-04.

## Approach notes

1. **How the tests run.** There is no Node on the host, but `node:20-alpine` is cached and the existing `node_modules` holds Linux ARM binaries, so tests, `tsc` and `eslint` run in a container with the folder mounted. Baseline before any change: 116 tests pass, `tsc` clean, `eslint` 0 errors and 5 existing warnings. This unit must not add a warning.
2. **A shared helper for labels** (`lib/duplicates.ts`) so the Ingestion results, the panel and the comparison read the same; month names are written out so the text never depends on a locale.
3. **Existing patterns reused**, not reinvented: TanStack Query for server state; the Radix dialog the Settings page already uses; the NavBar's badge polling convention; the `ApiError` body for error codes; Tailwind classes with `dark:` variants.
4. **No behaviour change to existing screens** except the two named: the Ingestion outcome cell for the new outcome, and enumerated settings becoming a dropdown.

## Steps

1. [x] **Types and API module** — modify `src/api/types.ts` (the new DTOs; `RunFileOutcome` gains `"skipped_probable_duplicate"`; `RunFileDetail` gains the two fields); create `src/api/duplicates.ts` with one function per endpoint (paths pinned at design).
2. [x] **Helpers** — create `src/lib/duplicates.ts`: `formatPeriod`, `formatStatementLabel`, `duplicateErrorMessage`.
3. [x] **Nav badge** — modify `src/components/NavBar.tsx`: `PendingDuplicatesBadge` beside the existing Review badge (violet, hidden at zero, accessible label, 30 s poll).
4. [x] **Panel** — create `src/components/DuplicateStatementsPanel.tsx` (the panel, its three groups, the idle and detection-off lines, Check again, pagination, in-flight polling, `DuplicatePairRow`, `RemovalConfirmDialog`); render it in `src/pages/ReviewPage.tsx` below the disagreement table.
5. [x] **Comparison page** — create `src/pages/ComparisonPage.tsx` (state banner, reason, headline figures, two side panels, text markers, `OverrideAction` with its two-step form for a removed copy); route `/duplicates/:comparisonId` in `src/App.tsx` inside the protected layout.
6. [x] **Ingestion results** — modify `src/pages/IngestionPage.tsx`: the outcome cell for a probable-duplicate skip is a link to its comparison.
7. [x] **Settings** — modify `src/pages/SettingsPage.tsx`: a dropdown for enumerated settings (keeping the existing test id) and "Duplicate Statements" in the category order.
8. [x] **Tests** — create `tests/duplicatesHelpers.test.ts`, the badge tests (placed in `NavBar.test.tsx`, where the other badges are tested), `tests/DuplicateStatementsPanel.test.tsx`, `tests/ComparisonPage.test.tsx`; extend `tests/IngestionPage.test.tsx`, `tests/SettingsPage.test.tsx`, `tests/NavBar.test.tsx`, `tests/ReviewPage.test.tsx` (the new panel must not break its existing mocks).
9. [x] **Verification** — run the whole suite, `tsc --noEmit` and `eslint` in the container (no new warning); a **mutation check** (one deliberate defect at a time: an information-only pair offering removal; the confirmation sending a count it did not show; the override on a removed copy needing only one click; the badge showing at zero; the removed group missing; the label helper ignoring the missing file name); each must make a test fail.
10. [x] **Documentation and progress** — `aidlc-docs/construction/frontend/code/probable-duplicate-summary.md`, update `frontend/code/README.md`, tick this plan, update `aidlc-state.md`.

## Completion criteria
- All steps `[x]`; the suite passes (the 116 existing tests unchanged); `tsc` clean; `eslint` with no new warning; the mutation check shows each safety property guarded; no file duplicated; no change outside `frontend/` and `aidlc-docs/`.

## Completion notes (2026-10-04)

All 10 steps done. 214 frontend tests pass (116 existing + 98 new); `tsc --noEmit` clean; `eslint` 0 errors and the same 5 pre-existing warnings; twelve mutations each caught. Details, the mutation table, and what was **not** verified (nothing has been viewed in a browser; no frontend-to-API contract test; the image is not rebuilt) are in `aidlc-docs/construction/frontend/code/probable-duplicate-summary.md`.

Differences from the plan as written: the existing tests' assertions are unchanged but four test files needed additive setup (a router wrapper, default mocks for the new calls, an optional settings list in a helper); the badge tests live in `NavBar.test.tsx` rather than a separate file; and the mutation check found one weak test (the side-title test checked that both headings existed, not which panel carried which), which was strengthened.

**Addendum (Build and Test, 2026-10-04)**: looked at in a real browser against a disposable stack. One change resulted: the comparison table spells each row's marker under its description on phone widths (the Match column was off-screen there). Frontend totals are now 215 tests (116 existing + 99 new) and fourteen mutations, each caught. A pre-existing "reload logs the user out" bug was found and filed as a separate task. See `construction/frontend/code/probable-duplicate-summary.md`.
