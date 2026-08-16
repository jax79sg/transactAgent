# Story Generation Plan — Local Embedding-Based Semantic Similarity

**Role**: Product owner, converting `embedding-similarity-requirements.md` into testable user stories.

## Conventions inherited from the approved project-wide story set — not re-asked

| Category | Convention | Why reused, not re-asked |
|---|---|---|
| Persona | Single persona, **The Account Owner** (`personas.md`) | This feature introduces no new user type. |
| Granularity | Coarse, epic-level capability stories | Matches every existing epic. |
| Acceptance criteria format | Given/When/Then happy path + explicit edge cases | Documentation-consistency call, not a product decision. |
| Traceability | Each story cites the FR/NFR IDs it satisfies | Direct carry-over from `embedding-similarity-requirements.md`. |
| Breakdown approach | One new epic, appended to the existing epic-numbered set | `stories.md` ends at Epic 5; `recategorization-review-stories.md` added Epic 6; `nightly-backup-stories.md` added Epic 7; `recurring-payments-stories.md` added Epic 8. This becomes **Epic 9: Local Embedding-Based Semantic Similarity**. |

## Genuinely open item

None. The 10-question round plus 2 rounds of clarification in `embedding-similarity-requirements.md` already
resolved every product decision needed for story-writing, including the two genuinely hard ones (runtime
identity, deployment topology). This plan has no `[Answer]:` questions.

## Execution Checklist

- [x] Draft **Epic 9: Local Embedding-Based Semantic Similarity**, one story per distinct user-visible
  outcome or safety-critical behavior (not one story per FR — several FRs describe internal mechanics with
  no separate user-facing moment):
  - [x] Story: see which transactions have a computed embedding (the badge) (FR-6, FR-7)
  - [x] Story: a repeat/paraphrased payment to the same payee gets matched via semantic similarity, without
    needing exact-enough text for the old fuzzy matcher (FR-1, FR-3, FR-4, FR-5)
  - [x] Story: the false-positive amount-gate protection still holds under embedding-based matching — same
    guarantee as today, new scoring method (FR-5, NFR-1) — explicit regression-style acceptance criteria,
    not just a requirements-doc line
  - [x] Story: ingestion and categorization keep working normally if the local embedding endpoint is down
    (FR-10)
  - [x] Story: existing (historical) transactions also get embeddings via the one-time backfill, not just
    newly-ingested ones (FR-11)
- [x] Write Given/When/Then happy path + edge cases for each story
- [x] Cite FR/NFR IDs on every story
- [x] Confirm `personas.md` needs no changes and state that explicitly
- [x] Create a feature-scoped stories file (`embedding-similarity-stories.md`)
- [x] Update `aidlc-state.md`

## Mandatory Artifacts

- [x] `embedding-similarity-stories.md` — new epic (US-9.1..9.5), INVEST-compliant stories with acceptance criteria
- [x] `personas.md` — reviewed, confirmed unchanged (single persona, The Account Owner)
