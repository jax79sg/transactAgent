# Story Generation Plan — Account Balance at a Point in Time

**Role**: Product owner, converting `account-balance-requirements.md` into testable user stories.

## Approach
Epic-based, following this project's established convention (Epics 6–12). This becomes **Epic 13: Account Balance at a Point in Time**, appended in a feature-scoped file (`account-balance-stories.md`) so the existing story set stays untouched.

## Conventions inherited from the approved project-wide story set — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | No new user type. The owner is also the person who triggers the one-time backfill (the persona is already described as comfortable running `docker-compose` commands). |
| Granularity | Coarse, epic-level capability stories, one per distinct FR cluster | Matches every existing epic. |
| Acceptance criteria format | Given/When/Then happy path plus explicit edge cases | Documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR/A-n IDs it satisfies | Direct carry-over from `account-balance-requirements.md`. |

## Genuinely open items

None. Two rounds of clarifying questions (11 in total) plus 8 documented assumptions in `account-balance-requirements.md` already resolved every product decision story-writing needs. Where a story's edge case depends on a documented assumption (A-1 to A-8), the acceptance criterion states the assumed behavior and cites the assumption, so the approval step on the stories doubles as a second review of those assumptions. This plan has no `[Answer]:` questions.

## Proposed story breakdown (Epic 13)

| Story | Capability | Requirements covered |
|---|---|---|
| US-13.1 | Accounts are identified automatically from my statements, and credit-card statements stay out of balances | FR-AB-1, FR-AB-2, FR-AB-4, A-1, A-2, A-3, NFR-AB-3, NFR-AB-8 |
| US-13.2 | I can tidy up my accounts: rename, merge, correct the type | FR-AB-3, A-3 |
| US-13.3 | I can tell the app a known real balance for each savings account | FR-AB-6, A-6, A-7 |
| US-13.4 | I can look up my balances for a specific date or month, per account and combined, in SGD | FR-AB-7, FR-AB-9, FR-AB-10, FR-AB-11, FR-AB-13, FR-AB-14, A-5, A-8, NFR-AB-1, NFR-AB-5 |
| US-13.5 | I can see how my balance changed over time | FR-AB-12, FR-AB-13, NFR-AB-7 |
| US-13.6 | I'm warned when a statement's closing balance disagrees with my computed balance | FR-AB-5, FR-AB-8, A-4 |
| US-13.7 | I can safely re-ingest my existing statements so history gains accounts and balances | FR-AB-15, FR-AB-16, FR-AB-17, NFR-AB-2 |

NFR-AB-4 (property-based and unit tests), NFR-AB-6 (authentication on new endpoints), and NFR-AB-7 (theme/responsive consistency) are cross-cutting constraints reflected across the stories rather than stories of their own, same treatment as the earlier epics' testing NFRs.

## Execution Checklist

- [x] Draft **Epic 13: Account Balance at a Point in Time**, one story per row of the table above
- [x] Write Given/When/Then happy path plus edge cases for each story, including the failure/guard states the requirements imply (account with no anchor, date after the latest ingested transaction, foreign-currency account with no FX rate, unknown account type, statement with no printed account identifier, correction that cannot be matched after reingest)
- [x] Cite FR/NFR/A-n IDs on every story
- [x] Confirm `personas.md` needs no changes and state that explicitly
- [x] Write a traceability summary table covering every FR-AB-1..17 and every NFR-AB-1..8, and state where each cross-cutting NFR lands (NFR-AB-4 and NFR-AB-6 are the cross-cutting ones, with no story of their own; all other NFRs and all FRs and assumptions map to a story)
- [x] Save as the feature-scoped `aidlc-docs/inception/user-stories/account-balance-stories.md`
- [x] Verify each story is Independent, Negotiable, Valuable, Estimable, Small, Testable (flag any that are not, with the reason): US-13.7 flagged as the largest, kept whole, may be split at Code Generation planning
- [x] Update `aidlc-state.md`

## Mandatory Artifacts

- [x] `account-balance-stories.md`: new epic, INVEST-compliant stories with acceptance criteria
- [x] `personas.md`: reviewed, confirmed unchanged
