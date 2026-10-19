# User Stories Assessment — Recategorization Algorithm Rework

## Request Analysis
- **Original Request**: Rework the retroactive recategorization re-scan's matching algorithm (broader precedent pool + independent LLM verification gate) after live evidence showed a 100% proposal-rejection rate since 2026-08-23; also rework the shared embedding-text construction (`build_embedding_text`) to add an in-flow/out-flow signal, applied across all 3 of its consumers (re-scan, `categorize()`, Recurring Payment Manager).
- **User Impact**: Indirect — the Review page and its existing approve/reject/auto-apply workflow are completely unchanged; only the *quality* of the categories the system proposes changes (fewer wrong proposals, more transactions correctly staying UNSURE instead of getting a bad guess).
- **Complexity Level**: Medium (spans one primary component plus a shared utility with 3 call sites, but no new component/service/UI/API surface).
- **Stakeholders**: Single user (project owner/sole user of this personal finance system) — no multi-persona or cross-team dimension.

## Assessment Criteria Met
- [ ] High Priority: None apply — no new user-facing feature, no UX/workflow change, not a customer-facing API, single persona, not a cross-team project.
- [x] Medium Priority: "Backend User Impact" applies (internal matching-quality change with an indirect, positive effect on what the user sees on the Review page).
- Complexity Assessment Factors (Medium Priority requires ANY to apply for stories to add value):
  - **Scope**: Spans 2 code areas (re-scan + shared embedding-text builder, 3 consumers) — some breadth, but all internal, no new user touchpoint.
  - **Ambiguity**: Already resolved — 2 rounds of clarifying questions (9 total) during Requirements Analysis already pinned down failure modes, scope boundaries, matching strategy, LLM-gate behavior, and embedding-text direction/de-weighting decisions. Little remaining ambiguity that story-writing would newly surface.
  - **Risk**: Real (live production data, 6000+ real transactions) — but risk here is about correctness/testing rigor at Build-and-Test time, not about needing user-centered narratives to clarify intent.
  - **Stakeholders**: Single user — no cross-persona alignment need.
  - **Testing**: User acceptance testing will happen (live-verify against real DB, same as every prior change in this project), but that's a Build-and-Test-stage activity independent of whether stories exist.
  - **Options**: Multiple valid implementation approaches existed (single-precedent vs. broader pool, LLM gate vs. none, global vs. scoped embedding-text change) — but these were the exact subject of the Requirements Analysis Q&A already conducted and resolved, not an open question stories would help resolve.
- [x] Benefits: Marginal for this specific request — the two prior recategorization-matching changes in this project (`recategorization-scope-narrowing-requirements.md`, and the earlier Matching Precision Refinement) both skipped User Stories with the same reasoning and went straight to Functional Design successfully.

## Decision
**Execute User Stories**: No

**Reasoning**: This is an internal algorithm-accuracy rework with zero new UI, zero new user workflow, and a single stakeholder. The Review page's approve/reject/auto-apply interaction the user already knows is completely unchanged — only match quality improves under the hood. The "Medium Priority" bucket is technically triggered (backend change with indirect user impact), but none of the complexity factors that would justify story-writing anyway (unresolved ambiguity, multiple stakeholders, open design options) actually apply here — the 2-round Requirements Analysis Q&A already did that clarifying work directly against the real code and real data, which is more precise for this kind of change than user-centered narratives would be. This matches the established precedent in this exact project: both prior recategorization-matching changes (`Recategorization Scope Narrowing`, `Matching Precision Refinement`) skipped User Stories for identical reasoning ("pure backend accuracy fix... no new user-facing workflow, no UI change") and proceeded straight to Workflow Planning / Functional Design.

## Expected Outcomes
N/A — stories skipped. Proceeding directly to Workflow Planning, which will determine per-unit Functional Design scope (Ingestion Worker Service only, per the Requirements Document's confirmed component boundary).
