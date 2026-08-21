# Execution Plan — Recategorization Scope Narrowing

## Detailed Analysis Summary

### Change Impact Assessment
- **User-facing changes**: Indirect only — fewer, more accurate recategorization proposals will appear on the Review page over time; the page itself, its columns, and its approve/reject flow are unchanged.
- **Structural changes**: No — no new component, no new method signature. Narrows the internal candidate-selection logic of an existing method (`recategorize_unsure_from_precedent`).
- **Data model changes**: No — `RecategorizationProposalSourceBucket.CATEGORIZED` stays in the enum for historical-row validity; no migration.
- **API changes**: No — no endpoint, request, or response shape changes.
- **NFR impact**: None new — if anything, a small `LOWER` (fewer DB rows scanned per correction, since Bucket B's full-table scan is removed).

### Component Relationships
- **Primary Component**: Ingestion Worker Service's Categorization Engine (`categorization/service.py`, `categorization/repository.py`).
- **Unaffected**: Database (no schema change), API Service (no DTO/endpoint change), Frontend SPA (no UI change — the existing `sourceBucket` display already handles both enum values, and will simply stop showing new "Already categorized" rows going forward while old ones stay visible until reviewed).

### Risk Assessment
- **Risk Level**: Low — removes a code path entirely rather than adding one; smaller surface area after the change than before.
- **Rollback Complexity**: Easy (revert one commit).
- **Testing Complexity**: Simple — remove/adjust the existing tests that exercised the now-deleted Bucket B branch; no new test scenarios to invent.

## Phases to Execute

### 🔵 INCEPTION PHASE
- [x] Workspace Detection (COMPLETED)
- [x] Requirements Analysis (COMPLETED)
- [x] User Stories (SKIPPED — pure backend accuracy fix, no user-facing workflow)
- [x] Workflow Planning (IN PROGRESS — this document)
- [ ] Application Design — **SKIP**
  - **Rationale**: No new component, no new method signature, no new dependency or communication pattern. This narrows the *internal* implementation of an existing method that Application Design already covers at the level it operates (`Categorization Engine Component`, `component-methods.md`'s `recategorizeFromPrecedent`-equivalent entry, unchanged signature).
- [ ] Units Generation — **SKIP**
  - **Rationale**: Existing unit (Ingestion Worker Service) only.

### 🟢 CONSTRUCTION PHASE
Single unit affected: **Ingestion Worker Service** only.

- [ ] Functional Design — **EXECUTE** (Ingestion Worker Service only)
  - **Rationale**: Revises established business rules WR-9/WR-10 in place — needs to be documented as a deliberate revision, not silently changed in code with no record.
- [ ] NFR Requirements — **SKIP**
  - **Rationale**: No new NFR concern; if anything this reduces per-correction DB load.
- [ ] NFR Design — **SKIP**
  - **Rationale**: Follows from NFR Requirements SKIP.
- [ ] Infrastructure Design — **SKIP**
  - **Rationale**: No new service, port, volume, or environment variable.
- [ ] Code Generation — **EXECUTE (ALWAYS)**
  - **Rationale**: Remove the Bucket B branch from `service.py`, delete the now-unused `find_categorized_transactions_excluding` repository query, update/remove the tests that exercised it.
- [ ] Build and Test — **EXECUTE (ALWAYS)**
  - **Rationale**: Verification needed before considering this complete, per project precedent.

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

## Success Criteria
- **Primary Goal**: Future manual corrections only trigger recategorization proposals against genuinely-`UNSURE` transactions — no more broad, low-accuracy proposals against already-categorized transactions.
- **Key Deliverables**: `service.py`'s Bucket B branch removed; `repository.py`'s now-dead query removed; `business-rules.md` WR-9/WR-10 revised in place with a dated note; tests updated; no schema/API/UI changes.
- **Quality Gates**: All Ingestion Worker Service unit tests passing (with the now-obsolete Bucket B tests removed, not just left failing); live verification that a manual correction only produces `UNSURE`-sourced proposals going forward.
