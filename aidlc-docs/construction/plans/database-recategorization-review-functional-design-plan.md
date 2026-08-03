# Functional Design Plan — Database Unit — Recategorization Review Panel

**Unit**: Database (Unit 1). **Scope**: one new entity, `RecategorizationProposal`, child of the existing `RecategorizationJob`.

## No blocking questions

The shape of this entity follows directly from decisions already made in Requirements Analysis (FR-RR-2) and Application Design (Recategorization Review Component's method signatures) — there is no genuine open business-logic question left for the Database unit specifically. It is structurally identical in spirit to the existing `IngestionRunFile` (a per-item child record of a parent job/run, with an outcome enum), so this plan reuses that established pattern rather than inventing a new one.

## Execution Checklist

- [ ] Add `RecategorizationProposal` entity to `domain-entities.md`, addendum-dated, matching the existing entity documentation format
- [ ] Add its ER diagram edge (child of `RecategorizationJob`, references `Transaction` twice — source and candidate)
- [ ] Add business rules to `business-rules.md` (starting at BR-14):
  - No duplicate pending proposal for the same candidate+source pair (NFR-RR-2)
  - A proposal's candidate must differ from its own source transaction (self-match exclusion, US-6.1)
  - Approving a proposal requires it to currently be `pending` (can't approve/reject twice)
- [ ] Add to `business-logic-model.md`: the auto-apply vs. pending decision as a described business process (not code), referencing the two-tier split from Application Design
