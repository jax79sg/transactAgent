# Story Generation Plan — Recurring Payments, Budget Alerts & Subscription Detection

**Role**: Product owner, converting `recurring-payments-requirements.md` into testable user stories.

## Conventions inherited from the approved project-wide story set — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | This feature introduces no new user type. |
| Granularity | Coarse, epic-level capability stories | Matches every existing epic. |
| Acceptance criteria format | Given/When/Then happy path + explicit edge cases | Documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR IDs it satisfies | Direct carry-over from `recurring-payments-requirements.md`. |
| Breakdown approach | One new epic, appended to the existing epic-numbered set | `stories.md` ends at Epic 5, `recategorization-review-stories.md` added Epic 6, `nightly-backup-stories.md` added Epic 7. This becomes **Epic 8: Recurring Payments & Budget Alerts**. |

## Genuinely open item

None. All 9 questions plus the follow-up in `recurring-payments-requirements.md` already resolved every product decision needed for story-writing. This plan has no `[Answer]:` questions.

## Execution Checklist

- [ ] Draft **Epic 8: Recurring Payments & Budget Alerts**, one story per distinct FR cluster:
  - [ ] Story: build and maintain the recurring payments register, one at a time (FR-1, FR-2)
  - [ ] Story: bulk-import an existing list (FR-3)
  - [ ] Story: see recurring payments on the Dashboard, with due/overdue status (FR-4, FR-9, FR-10, FR-11)
  - [ ] Story: review and approve/reject a proposed match (FR-5, FR-6, FR-8)
  - [ ] Story: trusted payments auto-match within tolerance, still review outside it (FR-7)
  - [ ] Story: get notified of untracked recurring charges (FR-12, FR-13)
  - [ ] Story: at-a-glance summary/badge of what needs attention (FR-14)
- [ ] Write Given/When/Then happy path + edge cases for each story
- [ ] Cite FR/NFR IDs on every story
- [ ] Confirm `personas.md` needs no changes and state that explicitly
- [ ] Append the new epic to a feature-scoped stories file (`recurring-payments-stories.md`)
- [ ] Update `aidlc-state.md`

## Mandatory Artifacts

- [x] `recurring-payments-stories.md` — new epic, INVEST-compliant stories with acceptance criteria
- [x] `personas.md` — reviewed, confirmed unchanged
