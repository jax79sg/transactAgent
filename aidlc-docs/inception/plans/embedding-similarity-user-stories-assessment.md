# User Stories Assessment — Local Embedding-Based Semantic Similarity

## Request Analysis
- **Original Request**: Compute local embeddings for transaction descriptions (oMLX-served `embeddinggemma-300m`), store them in a vector DB, surface a transaction-list badge, and use embedding-based similarity (with the existing fuzzy-text matcher as fallback) across categorization, recategorization, recurring-payment matching, and detection.
- **User Impact**: Direct, though narrow — one new visible element (the embedding-status badge, FR-7) plus an indirect, invisible-to-the-user improvement in categorization accuracy across three existing features.
- **Complexity Level**: Complex (multi-component: Database, Ingestion Worker, API Service, Frontend; a new external dependency; a decision-order change to existing business logic in three places).
- **Stakeholders**: Single persona — The Account Owner (`personas.md`); this feature introduces no new persona.

## Assessment Criteria Met
- [x] High Priority: "New User Features" — the embedding-status badge (FR-7) is a new, directly-visible UI element.
- [x] High Priority: "Complex Business Logic" — FR-3/FR-4/FR-5's embedding-first-then-fuzzy-fallback decision order, applied across three existing matching call sites (Categorization Engine, Recurring Payment Manager, Detection Scan), benefits from concrete Given/When/Then scenarios rather than being left as prose, exactly the pattern this project's prior epics (6, 7, 8) found valuable.
- [x] Medium Priority / Complexity Factors: "Scope" spans all 4 units; "Risk" — this changes categorization behavior for existing, already-working features, and NFR-1 (the AXS amount-gate carryover) is safety-critical enough to deserve an explicit acceptance-criteria scenario, not just a requirements-doc line.

## Decision
**Execute User Stories**: Yes
**Reasoning**: Meets multiple Always-Execute indicators independently (new user-facing badge, complex cross-cutting business logic); follows the same pattern already established by Epics 6, 7, and 8 in this project. (Contrast with the immediately-prior WR-20 fix, which correctly skipped Stories as a purely internal, single-file change — this feature is neither.)

## Expected Outcomes
- Concrete Given/When/Then scenarios for the embedding-first/fuzzy-fallback decision order, the badge's async timing, endpoint-failure behavior, and the amount-gate carryover — the details most likely to be subtly wrong if left as prose.
- A new epic (Epic 9) added to the project's story set, traceable to FR-1..11, ready to feed Workflow Planning and Application Design.
