# Application Design Plan: Categorization Model Fine-Tuning

## Plan

- [x] Generate `components.md` addenda — new **Model Training** unit (Dataset Curator + Fine-Tuning Trainer components), plus a scoped extension to the existing Categorization Engine Component (FR-CFT-9)
- [x] Generate `component-methods.md` addenda — method signatures for the 2 new components; `classify`/`classifyBatch` signature change
- [x] Generate `services.md` addendum — Model Training's orchestration pattern (2 manual CLI scripts, no service loop)
- [x] Generate `component-dependency.md` addenda — dependency matrix rows, communication-pattern bullets, and a new self-contained data-flow diagram for the read-only Shared DB relationship
- [x] Generate `application-design.md` consolidated addendum
- [x] Validate design completeness and consistency against approved requirements (FR-CFT-1..10, NFR-CFT-1..6 all traced to a component)

## Key Design Decisions

No blocking clarifying questions were raised at this stage — the approved requirements document (`categorization-model-finetuning-requirements.md`) had already resolved every genuinely ambiguous point during Requirements Analysis (including two dedicated clarification rounds). The decisions below are direct, requirements-consistent design calls, not open questions:

1. **Component breakdown — 2 components, not 3**: FR-CFT-10 already implies two standalone CLI scripts (curate, then train). Rather than splitting "Trainer" and "Evaluator" into separate components, evaluation (FR-CFT-7) is kept inside the Fine-Tuning Trainer Component as a method (`evaluate()`) called at the end of `train()` — it always runs as part of a training pass (there's no standalone "evaluate an already-trained model" requirement), so a separate component would be a distinction without a difference at this design level.

2. **Reuse `transactagent_db` for DB access, not a new data-access layer**: The existing shared internal package (already depended on by both API Service and Ingestion Worker Service for their DB models) is the natural, idiomatic way for the Dataset Curator to read `transactions`/`recategorization_proposals`/`categorization_disagreements`. NFR-CFT-1's environment-isolation requirement is about the *heavyweight ML dependencies* (mlx-tune, ClearML) needing their own environment — it doesn't imply duplicating the DB layer too. Writing a second, parallel ORM/query layer just to avoid a shared dependency would be inconsistent with this project's existing "one schema, shared package, separate deployables" pattern (see `component-dependency.md`'s Shared DB section).

3. **No new component for "external ML services"**: HuggingFace Hub (model download) and ClearML (run tracking) are both simple, one-directional outbound calls with no data flowing back into this project's own systems — same treatment the existing Drive Connector/Currency Conversion/LLM API dependencies already get (a dependency-matrix row + prose, not a dedicated component wrapping them).

4. **`evaluate()`'s live-model comparison is read-only, not a new integration pattern**: FR-CFT-7b's "agreement rate vs. the current live model" is implemented as `Fine-Tuning Trainer Component.evaluate()` calling the already-existing (post-FR-CFT-9) categorization path the same way any other caller would — not a new API endpoint, not a new coordination mechanism. This keeps Model Training a true leaf/offline component: nothing on the API Service or Ingestion Worker Service side needs to know it exists.

## Result

Complete — see `application-design.md`'s "Addendum (2026-08-17)" section for the full requirement-to-component traceability table. No gaps, no speculative components.
