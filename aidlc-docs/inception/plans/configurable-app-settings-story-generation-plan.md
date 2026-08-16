# Story Generation Plan — Configurable Application Settings

**Role**: Product owner, converting `configurable-app-settings-requirements.md` into testable user stories.

## Conventions inherited from the approved project-wide story set (`stories.md`) — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | This feature introduces no new user type — the same sole user who already edits categories (US-5.2) and configures `.env` (US-5.3) is who edits these settings. |
| Granularity | Coarse, epic-level capability stories | Matches every existing epic in `stories.md`; mixing granularity within one story set would hurt readability, not this feature's quality. |
| Acceptance criteria format | Given/When/Then happy path + explicit edge cases | Same reasoning — a documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR IDs it satisfies | Direct carry-over from `configurable-app-settings-requirements.md`'s FR-CAS-1..10 / NFR-CAS-1..6. |
| Breakdown approach | One new epic, appended to the existing epic-numbered set | `stories.md`'s epics currently run through Epic 9 (`embedding-similarity-stories.md`; Matching Precision Refinement skipped stories). This becomes **Epic 10: Configurable Application Settings**. Feature-based, matching how every prior post-completion feature was scoped as its own new epic even when thematically extending an existing one (e.g. Recategorization Review extended Epic 2's theme but became Epic 6, not an addition to Epic 2) — Epic 5 (Access & Configuration) is this feature's closest thematic sibling (it already covers editing the category whitelist and `.env`-based configuration), but per that same precedent this becomes its own epic rather than an in-place edit to Epic 5. |

## Genuinely open item (flagged, not blocking)

The requirements doc fixed *where* this lives (a new section on the existing Settings page, FR-CAS/Resolved Decision 5) but not what that section is called. Rather than open another question round for a copy decision:

> **Assumption**: the new section is titled **"Application Settings"**, with its riskier subset visually grouped under an **"Advanced"** sub-heading (matching the requirements doc's own "Advanced" terminology). If you'd prefer different wording, flag it at the stories approval gate below — it's a one-line change with no ripple into requirements.

No other category (user personas, granularity, format, breakdown, acceptance criteria, business context, technical constraints) has open ambiguity — each is either inherited from the approved project convention above or already resolved in `configurable-app-settings-requirements.md`. This plan therefore has no `[Answer]:` questions to fill in; it's presented for approval, not for input.

## Execution Checklist

- [x] Draft **Epic 10: Configurable Application Settings**, containing one story per distinct capability:
  - [x] Story: view and edit a standard setting — current value, validation, confirmation, save, restart-required guidance (FR-CAS-1, FR-CAS-3, FR-CAS-4, FR-CAS-6, FR-CAS-8, FR-CAS-10; edge cases covering NFR-CAS-1/NFR-CAS-2's exclusion boundary and NFR-CAS-3's override-file-not-`.env` distinction as it's user-observable via what does/doesn't need a restart)
  - [x] Story: Advanced settings are clearly distinguished and warn before edit (FR-CAS-2)
  - [x] Story: Ingestion Worker busy/idle indicator gates the restart-safe guidance (FR-CAS-7, NFR-CAS-5)
  - [x] Story: view settings change history (FR-CAS-9, NFR-CAS-6)
- [x] Write Given/When/Then happy path + edge cases for each story, matching `stories.md`'s existing depth
- [x] Cite FR-CAS/NFR-CAS IDs on every story
- [x] Confirm `personas.md` needs no changes (single persona, already covers this feature) and state that explicitly rather than silently skipping the mandatory-artifact checklist item
- [x] Append the new epic to a feature-scoped stories file (`configurable-app-settings-stories.md`) rather than editing the original `stories.md`/other feature files in place
- [x] Update `aidlc-state.md`'s Post-Completion Change section

## Mandatory Artifacts

- [x] `configurable-app-settings-stories.md` — new epic, INVEST-compliant stories with acceptance criteria (this feature's stories only)
- [x] `personas.md` — reviewed, confirmed unchanged (documented above, not silently skipped)
