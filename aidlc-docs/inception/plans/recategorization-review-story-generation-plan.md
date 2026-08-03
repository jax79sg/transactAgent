# Story Generation Plan — Recategorization Review Panel

**Role**: Product owner, converting `recategorization-review-requirements.md` into testable user stories.

## Conventions inherited from the approved project-wide story set (`stories.md`) — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | This feature introduces no new user type — the same sole user who corrects categories today is who reviews proposals. |
| Granularity | Coarse, epic-level capability stories | Matches every existing epic in `stories.md`; mixing granularity within one story set would hurt readability, not this feature's quality. |
| Acceptance criteria format | Given/When/Then happy path + explicit edge cases | Same reasoning — this is a documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR IDs it satisfies | Direct carry-over from `recategorization-review-requirements.md`'s FR-RR-1..10 / NFR-RR-1..4. |
| Breakdown approach | One new epic, appended to the existing epic-numbered set | `stories.md` currently ends at Epic 5; this becomes **Epic 6: Recategorization Review**. Feature-based, not persona- or journey-based, matching how every existing epic is scoped (Epic 2 = Categorization & Learning is the closest sibling — this epic extends it). |

## Genuinely open item (flagged, not blocking)

The requirements doc deliberately deferred the new page's exact name/nav label to this stage. Rather than open another question round for a copy decision, the plan below picks a name and states it as an explicit, reviewable assumption:

> **Assumption**: the new page is titled **"Review"** with nav label **"Review"**, and the panel's items are called **proposals** throughout (matching the requirements doc's own terminology). If you'd prefer different wording, flag it at the stories approval gate below — it's a one-line change with no ripple into requirements.

No other category (user personas, granularity, format, breakdown, acceptance criteria, business context, technical constraints) has open ambiguity — each is either inherited from the approved project convention above or was already resolved in `recategorization-review-requirements.md`. This plan therefore has no `[Answer]:` questions to fill in; it's presented for approval, not for input.

## Execution Checklist

- [ ] Draft **Epic 6: Recategorization Review**, containing one story per distinct FR-RR cluster:
  - [ ] Story: broadened candidate search on manual correction (FR-RR-1, FR-RR-2)
  - [ ] Story: high-confidence auto-apply for the UNSURE bucket (FR-RR-3)
  - [ ] Story: everything else routes to review, never silently overwriting an already-categorized transaction (FR-RR-4)
  - [ ] Story: reviewing and approving/rejecting proposals, individually and in bulk (FR-RR-5, FR-RR-6, FR-RR-7)
  - [ ] Story: rejected/ignored proposals leave transactions untouched with no suppression memory (FR-RR-8)
  - [ ] Story: pending-count visibility in navigation (FR-RR-9)
- [ ] Write Given/When/Then happy path + edge cases for each story, matching `stories.md`'s existing depth
- [ ] Cite FR-RR/NFR-RR IDs on every story
- [ ] Confirm `personas.md` needs no changes (single persona, already covers this feature) and state that explicitly rather than silently skipping the mandatory-artifact checklist item
- [ ] Append the new epic to a feature-scoped stories file (`recategorization-review-stories.md`) rather than editing the original `stories.md` in place, preserving the original project's history
- [ ] Update `aidlc-state.md`'s Post-Completion Change section

## Mandatory Artifacts

- [x] `recategorization-review-stories.md` — new epic, INVEST-compliant stories with acceptance criteria (this feature's stories only)
- [x] `personas.md` — reviewed, confirmed unchanged (documented above, not silently skipped)
