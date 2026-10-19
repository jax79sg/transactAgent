# Frontend Code Summary — Probable Duplicate Statement Detection (Epic 14)

**Unit**: Frontend (Unit 4). **Stories**: US-14.1 to US-14.6 (the visible side). **Plan**: `aidlc-docs/construction/plans/frontend-probable-duplicate-code-generation-plan.md`. **Design**: `construction/frontend/functional-design/` (the Epic 14 sections) and the API's pinned endpoint paths.
**Status**: code and tests complete, uncommitted on `feature/account-balance` (one PR for Epics 13 and 14). Looked at in a real browser against a disposable stack at Build and Test (2026-10-04) — see "Looked at in a browser".

## What a person can now do

| Where | What appears | Story |
|---|---|---|
| **Ingestion → run results** | A file skipped as a probable duplicate reads "Probable duplicate of *JUN 2026_0728.pdf (UOB, 2 Jun to 30 Jun 2026)*", a link to the stored comparison. The same text appears in every later run that meets the file again. | US-14.1, 14.2, 14.4 |
| **`/duplicates/:comparisonId`** (new page) | The reason in words, the headline figures (both sizes, both periods, how many matched), and the two stored snapshots side by side, every row marked in words ("Also on the other statement" / "Only on this one"), never by colour alone. A state banner says what happened to the file. A "Not a duplicate — ingest it" button; for a *removed* copy it takes a second, deliberate click after a warning that the copy's manual corrections are not restored. | US-14.2, 14.3 |
| **Review → Duplicate Statements** (new panel, below the disagreements) | Three groups: *Being removed*, *Awaiting your decision*, *Removed in the last 24 hours*. Each pair shows the copy to **keep** and the copy to **remove** with sizes and manual-correction counts. Actions: View comparison, Remove duplicate…, Not a duplicate — dismiss. A pair of clearly different sizes is **information only** (dismiss, no remove); a pair with a missing statement is **stale** (dismiss only). "Check again" and the last-checked line; "detection is switched off" with a link to Settings when it is. | US-14.5 |
| **Remove duplicate… (confirmation)** | States exactly what will be permanently deleted (transactions, account sections, jobs, proposals, disagreements, recurring matches — zero kinds are not listed), that the search embeddings go too, how many transactions exist only on this copy, and how many manual corrections will be lost. The request carries the hash of the copy and the **exact correction count the dialog showed**, so the server can refuse if it changed. | US-14.6 |
| **Nav bar** | A violet badge on *Review*, beside the existing recategorization badge, counting pairs awaiting a decision (information-only pairs included until dismissed). Hidden at zero; read aloud as words ("3 duplicate statements awaiting review"). | US-14.5 |
| **Settings** | "Duplicate Statements" category. Enumerated settings (the first being the on/off switch, whose values are `false`/`true`) are now a dropdown of the allowed values instead of a text box. Saving still goes through the existing confirmation dialog. | NFR-PD-5 |

## Files

**Created** (`frontend/`)
- `src/api/duplicates.ts` — one function per endpoint (`listPairs`, `getPendingPairCount`, `getComparison`, `requestRemoval`, `dismissPair`, `overrideSkippedFile`, `getScanStatus`, `requestRecheck`).
- `src/lib/duplicates.ts` — `formatPeriod` (month names written out, so text never depends on a locale), `formatStatementLabel` (falls back from file name to bank and period to "a statement"), `duplicateErrorMessage`, `errorCode`, `STALE_ACTION_ERRORS`.
- `src/components/DuplicateStatementsPanel.tsx` — the panel, its groups, `PairRow`, `RemovalConfirmDialog` (Radix, as the Settings page already uses).
- `src/pages/ComparisonPage.tsx` — banner, reason, figures, two side panels, `OverrideAction`.

**Modified** (`frontend/`)
- `src/api/types.ts` — new DTO types; `RunFileOutcome` gains `"skipped_probable_duplicate"`; `RunFileDetail` gains two optional fields.
- `src/components/NavBar.tsx` — `PendingDuplicatesBadge`.
- `src/pages/ReviewPage.tsx` (panel), `src/pages/IngestionPage.tsx` (outcome link), `src/pages/SettingsPage.tsx` (dropdown, category order), `src/App.tsx` (route, inside the protected layout).

## Behaviour that matters

- **Nothing happens without the person's click.** The panel only ever *requests* a removal; the worker re-verifies and executes. Removal is never offered when `removalOffered` is false (information-only), and the page trusts the server's `canOverride` rather than inferring it from the state.
- **A stale decision cannot go through.** When the server answers `confirmation_out_of_date`, `pair_not_pending`, `removal_not_offered`, `statement_missing` or `removal_already_requested`, the dialog closes, the list refreshes, a plain-words notice says what happened, and nothing was deleted. Any other error keeps the dialog open so the person can retry or cancel.
- **One refresh keeps everything in step.** Every action invalidates the `["duplicates"]` query prefix, so the list, the badge and the scan status never disagree.
- **Polling is cheap.** The panel polls every 3 s only while a removal is in flight; the badge uses the existing 30 s ambient poll.
- **A failed removal can be retried**: it shows its reason and the actions return.
- **Existing screens unchanged** except the two named (the Ingestion outcome cell for the new outcome, and enumerated settings as a dropdown).

## Test results

| Check | Result |
|---|---|
| Whole frontend suite | **215 pass** (116 existing + 99 new), 20 files |
| `tsc --noEmit` | clean |
| `eslint` | 0 errors; the same 5 pre-existing `react-refresh` warnings, none added |
| act() warnings from the new tests | none (one test initially produced 12 by ending before its dialog closed; fixed) |

New tests: `duplicatesHelpers` 18, `DuplicateStatementsPanel` 33, `ComparisonPage` 33, `NavBar` +5, `IngestionPage` +4, `SettingsPage` +4, `ReviewPage` +2.

The existing tests' assertions are unchanged. Their *setup* changed in four files, all additive: `IngestionPage` tests now render inside a `MemoryRouter` (the outcome cell uses a `Link`); `ReviewPage` tests default the two duplicates calls; `NavBar` tests default the pending-count call (without it, every NavBar test logged "query data cannot be undefined"); the `SettingsPage` render helper takes an optional settings list.

### Mutation check (a scratch copy, one deliberate defect at a time — each must fail a test)

| # | Defect | Caught by |
|---|---|---|
| M1 | an information-only pair offers Remove | panel: information-only and stale tests |
| M2 | the confirmation sends a correction count it did not show | panel: "EXACTLY the correction count the dialog showed" |
| M3 | override of a removed copy takes one click | comparison: second-click and cancel tests |
| M4 | the badge shows at zero | NavBar: no-duplicates test |
| M5 | the "Removed" group is missing | panel: three tests |
| M6 | the label helper ignores a missing file name | helpers (2) and comparison (1) |
| M7 | stale-action errors leave the dialog open | panel: all five error codes |
| M8 | the list polls when nothing is in flight | panel: "does NOT poll" |
| M9 | the "This file" / "The statement it matches" titles swapped | comparison (after the fix below) |
| M10 | a failed removal is not offered again | panel: failed-removal test |
| M11 | the raw outcome code shown instead of the link | ingestion (2) |
| M12 | an enumerated setting edited with a text box | settings (2) |

**M9 survived the first time** and exposed a real weakness in my test: it checked that both headings existed, not which panel carried which, so swapped titles passed. The test now asserts each panel's own heading and that the panel called "This file" holds the skipped file; M9 is then caught. Twelve of twelve are guarded. Two more were added when the browser check led to a phone-width change (M13: the marker line under the description removed; M14: the Match column not hidden below `sm`), both caught: fourteen of fourteen.

## Looked at in a browser (Build and Test, 2026-10-04)

A disposable stack was built for this and torn down afterwards: a throwaway PostgreSQL, the **real** API app and the **real** worker code (used to seed: two downloads of each of four statements ingested with detection off, the pair scan, a completed removal through the real handler, a removal left in flight, and a second run with detection on), and the Vite dev server (later also a production build). The live stack was not touched (its five containers stayed up and healthy; the browser's network log showed no request to the live API's port). Seen: the nav badge (violet, with the right number, falling from 2 to 1 as soon as a removal was requested), all three panel groups and the information-only pair, the removal confirmation with both warnings, the in-flight state after confirming, the comparison page for a removed copy, a skipped file and an information-only pair, both new outcomes in the run results, the Settings category and its dropdown, dark and light themes, and a 375 px phone viewport.

Findings:
1. **Fixed here — the comparison table hid its evidence on a phone.** The Match column (the words "Also on the other statement" / "Only on this one") was pushed off-screen inside the table's scroll area and the amount was clipped. On narrow screens each row now spells the marker under its description and the separate column is hidden below the `sm` breakpoint; one new test and two new mutation checks guard it. Re-checked in the browser.
2. **Not caused by this work, filed separately — a hard reload logs the user out.** A reload (or opening a page by its address) with a valid session ends at the login page. Cause: `AuthProvider` hands the token to the API client in a `useEffect`, after child components have already sent their first requests without it; those get 401 and the central handler logs out. Reproduced on the dev server and on a production build; the three existing NavBar queries are among the first requests affected, and `AuthContext.tsx` / `client.ts` are untouched here. A separate task was raised with the evidence and a likely fix. It does not affect this feature's tests or behaviour.
3. **Existing, not changed:** a React "unique key" console warning from `IngestionPage` (a fragment around the run-history rows needs a key).

Still not verified: the container image has not been rebuilt, so the running app still serves the old frontend; nothing was looked at on a real phone (a 375 px emulated viewport only); the browser check used generated statements (UOB, Trust, DBS and CIMB shapes), not the user's real ones.

## What a frontend-to-API contract looks like now

Closed at Build and Test: `integration-tests/contract_check_probable_duplicates.py` compares the API's real output with `types.ts` and `duplicates.ts` (100 items: field names, nullability, enumerated values against the database enums and the service's state strings, and all eight routes with methods). It passes, and was shown to fail on a renamed field, enum typos and wrong routes. A cross-service scenario in the same folder exercises worker, API and the data flow between them (see the Build and Test summary).

## Differences from the plan as written

1. The plan said the 116 existing tests would stay "unchanged"; their assertions are, but four files needed additive setup (above).
2. The plan listed a separate `tests/PendingDuplicatesBadge.test.tsx`; the badge tests live in `NavBar.test.tsx`, where the other badges are tested.
3. The mutation check found one weak test (M9), which was strengthened.
4. Testing needed a harness fix worth recording: a scratch copy with a read-only `node_modules` mount makes vite fail to start, and an empty result must be reported as a harness error, not as a surviving mutation — the first run printed three false "SURVIVED" lines for exactly that reason before it was corrected.
5. The browser check at Build and Test led to one change after this summary was first written: the phone-width marker line under each description in the comparison table (finding 1 above).
