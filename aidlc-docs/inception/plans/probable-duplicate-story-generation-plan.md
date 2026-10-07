# Story Generation Plan — Probable Duplicate Statement Detection

**Role**: Product owner, converting `probable-duplicate-statements-requirements.md` into testable user stories.

## Approach
Epic-based, following this project's established convention (Epics 6 to 13). This becomes **Epic 14: Probable Duplicate Statement Detection**, in a feature-scoped file (`probable-duplicate-stories.md`) so the existing story set stays untouched.

## Conventions inherited from the approved project-wide story set — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | No new user type. |
| Granularity | Coarse, epic-level capability stories, one per distinct FR cluster | Matches every existing epic. |
| Acceptance criteria format | Given/When/Then happy path plus explicit edge cases | Documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR/A-PD IDs it satisfies | Carry-over from the requirements document. |

## Genuinely open items

None. Two rounds of clarifying questions (8 in total) plus 8 documented assumptions already resolved every product decision story-writing needs. Where an edge case rests on an assumption (A-PD-1 to A-PD-8), the acceptance criterion states the assumed behavior and cites it, so approving the stories doubles as a second review of those assumptions. This plan has no `[Answer]:` questions.

## Proposed story breakdown (Epic 14)

| Story | Capability | Requirements covered |
|---|---|---|
| US-14.1 | A probable duplicate is skipped automatically, and I am told why | FR-PD-1, FR-PD-2, FR-PD-3, FR-PD-4, NFR-PD-1, NFR-PD-6, A-PD-1, A-PD-2, A-PD-3, A-PD-7 |
| US-14.2 | I can see the evidence and be sure it really is a duplicate | FR-PD-5, FR-PD-6, A-PD-3 |
| US-14.3 | If it is not a duplicate, I can ingest it anyway | FR-PD-7, A-PD-4 |
| US-14.4 | A flagged or removed file is not re-read on every run | FR-PD-8, FR-PD-13, NFR-PD-2, A-PD-8 |
| US-14.5 | I can see duplicates already in my data and decide what to do | FR-PD-9, FR-PD-10, FR-PD-11, A-PD-5, A-PD-6 |
| US-14.6 | Removing a confirmed duplicate is safe and complete | FR-PD-11, FR-PD-12, FR-PD-13, FR-PD-14, NFR-PD-3, NFR-PD-4 |
| US-14.7 | The Account Balance backfill handles duplicates without losing my work | FR-PD-15, FR-PD-16, FR-PD-17, FR-PD-18, NFR-PD-5 |

NFR-PD-7 (property-based and conventional tests) and NFR-PD-8 (theme, responsive behavior, and authentication on new endpoints) are cross-cutting constraints reflected across the stories rather than stories of their own.

## Execution Checklist

- [x] Draft **Epic 14: Probable Duplicate Statement Detection**, one story per row of the table above
- [x] Write Given/When/Then happy path plus edge cases for each story, including the guard states the requirements imply (the UOB and Trust June pairs flagged; the CIMB one-transaction look-alikes not flagged; a statement under 3 transactions; a flagged file that stays in Drive; both copies carrying manual corrections; two duplicates arriving in one run; a false positive recovered by the override; a removed copy's file still in Drive; the backfill skipping a copy that held corrections)
- [x] Cite FR/NFR/A-PD IDs on every story
- [x] Confirm `personas.md` needs no changes and state that explicitly
- [x] Write a traceability summary table covering every FR-PD-1..18 and every NFR-PD-1..8, and state where each cross-cutting NFR lands
- [x] Save as the feature-scoped `aidlc-docs/inception/user-stories/probable-duplicate-stories.md`
- [x] Verify each story is Independent, Negotiable, Valuable, Estimable, Small, Testable (flag any that are not, with the reason)
- [x] Update `aidlc-state.md`

## Mandatory Artifacts

- [x] `probable-duplicate-stories.md`: new epic, INVEST-compliant stories with acceptance criteria
- [x] `personas.md`: reviewed, confirmed unchanged
