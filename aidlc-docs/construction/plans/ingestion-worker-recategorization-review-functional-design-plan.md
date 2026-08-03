# Functional Design Plan — Ingestion Worker Service Unit — Recategorization Review Panel

**Unit**: Ingestion Worker Service (Unit 3). **Scope**: broaden and split the existing FR-5.4 retroactive re-scan (WR-5) inside the Categorization Engine Component — no new component.

## No blocking questions

Every business rule needed follows directly from the approved Requirements/Application Design (the auto-apply-only-for-UNSURE resolution in particular), and the algorithm is a direct, minimal extension of the existing `recategorize_unsure_from_precedent` — same similarity matcher, same no-LLM constraint (WR-5), one new threshold and one new candidate-source query. The exact numeric value of the new auto-apply threshold is deferred to Code Generation, consistent with WR-3's own established precedent ("tuned during Code Generation/testing — not hardcoded to an arbitrary number here").

## Execution Checklist

- [x] Add WR-9 (broadened search + two-tier split) and WR-10 (already-categorized bucket never auto-applies, self/no-op exclusion) to `business-rules.md`
- [x] Add an addendum to `business-logic-model.md`'s Categorization Engine section describing the split algorithm and what the function's return value now means
- [x] Add an addendum to `domain-entities.md` noting no new internal DTO is needed (writes proposal rows directly, matching the existing pattern)
