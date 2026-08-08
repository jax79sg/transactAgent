# Story Generation Plan — Nightly Transaction Backup

**Role**: Product owner, converting `nightly-backup-requirements.md` into testable user stories.

## Conventions inherited from the approved project-wide story set (`stories.md`) — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | This feature introduces no new user type — the same sole user who relies on Drive-based ingestion is who benefits from and monitors the backup. |
| Granularity | Coarse, epic-level capability stories | Matches every existing epic in `stories.md` and `recategorization-review-stories.md`; mixing granularity within one story set would hurt readability, not this feature's quality. |
| Acceptance criteria format | Given/When/Then happy path + explicit edge cases | Same reasoning — a documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR IDs it satisfies | Direct carry-over from `nightly-backup-requirements.md`'s FR-1..11 / NFR-1..4. |
| Breakdown approach | One new epic, appended to the existing epic-numbered set | `stories.md` ends at Epic 5; `recategorization-review-stories.md` added Epic 6. This becomes **Epic 7: Nightly Transaction Backup**. Feature-based, matching every existing epic. |

## Genuinely open item (flagged, not blocking)

None. Both rounds of clarifying questions in `nightly-backup-requirements.md` (initial + follow-up) already resolved every product decision needed for story-writing: backup scope, destination folder structure, retention semantics, catch-up behavior, failure/no-retry rule, and the Review-page panel's placement and dual failure-mode display. This plan therefore has no `[Answer]:` questions to fill in; it's presented for approval, not for input.

## Execution Checklist

- [ ] Draft **Epic 7: Nightly Transaction Backup**, containing one story per distinct FR cluster:
  - [ ] Story: automatic nightly full-snapshot export to the dedicated backup Drive folder (FR-1, FR-2, FR-3, FR-4, FR-5, FR-6)
  - [ ] Story: retention keeps exactly the 7 most recent backups, safely scoped (FR-7, NFR-4)
  - [ ] Story: a missed nightly backup catches up once the worker is back online (FR-8)
  - [ ] Story: a failed backup does not retry same-night, and is visible without reading logs (FR-9, FR-10, FR-11)
- [ ] Write Given/When/Then happy path + edge cases for each story, matching `stories.md`'s existing depth
- [ ] Cite FR/NFR IDs on every story
- [ ] Confirm `personas.md` needs no changes (single persona, already covers this feature) and state that explicitly rather than silently skipping the mandatory-artifact checklist item
- [ ] Append the new epic to a feature-scoped stories file (`nightly-backup-stories.md`) rather than editing the original `stories.md` or `recategorization-review-stories.md` in place, preserving prior history
- [ ] Update `aidlc-state.md`'s Post-Completion Change section

## Mandatory Artifacts

- [x] `nightly-backup-stories.md` — new epic, INVEST-compliant stories with acceptance criteria (this feature's stories only)
- [x] `personas.md` — reviewed, confirmed unchanged (documented above, not silently skipped)
