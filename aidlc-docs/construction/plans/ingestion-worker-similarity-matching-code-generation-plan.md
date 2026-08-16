# Code Generation Plan — Ingestion Worker Service: Similarity-Matching Normalization

## Unit Context
- **Unit**: Ingestion Worker Service (Categorization Engine component only)
- **Stories**: None (User Stories stage skipped for this feature — pure internal accuracy fix)
- **Traces to**: `similarity-matching-requirements.md` FR-1..FR-7, NFR-1..NFR-3; `business-rules.md` WR-20
- **Dependencies**: None new — pure stdlib `re`, no new package dependency
- **Files touched**: `ingestion-worker/src/ingestion_worker/categorization/similarity.py` (modify in place),
  `ingestion-worker/tests/test_similarity.py` (extend in place)
- **No other files change** — `service.py`'s call sites already pass description/candidates through to
  `find_best_match`; normalization happens inside that function, so no call-site signature changes.

## Steps

### Step 1: Business Logic Generation
- [x] Add `normalize_reference_noise(description: str) -> str` to `similarity.py`: two compiled module-level
  regexes (digit-run `\b\d{3,}\b`, short-mixed `\b(?=[A-Za-z0-9]{1,12}\b)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+\b`)
  applied in order, then whitespace collapse — exactly as validated in Functional Design (WR-20).
- [x] Update `find_best_match` to normalize both `description` and each `c.description` before calling
  `fuzz.token_sort_ratio` (FR-4: both sides, every comparison).
- [x] Add a short docstring note on `normalize_reference_noise` referencing WR-20, consistent with this
  file's existing docstring style (see `amounts_in_range`'s AXS-incident note).

### Step 2: Business Logic Unit Testing
- [x] Add example-based tests to `test_similarity.py`:
  - The 3 diagnosis examples, each as a same-payee repeat-payment pair (differing only in reference/QR
    code), asserting score ≥ `similarity_threshold` (85.0) via `find_best_match`.
  - A cross-payee sanity case confirming unrelated payees still score well below threshold.
  - Direct unit tests of `normalize_reference_noise` itself for the two token shapes and the "payee text
    untouched" property (FR-3).
- [x] Add property-based test(s) to `test_similarity.py` (Hypothesis) consistent with this file's existing
  Partial-PBT convention (NFR-1) — e.g., normalization never lengthens the string, and normalizing twice is
  idempotent.
- [x] Re-run existing `TestAmountRangeGating` class unchanged — confirm both AXS tests and the CCY-conversion
  small-value test still pass (NFR-2 regression protection). Full suite: 179/179 passed (up from 168).

### Step 3: Business Logic Summary
- [x] Create `aidlc-docs/construction/ingestion-worker/code/similarity-matching-normalization-summary.md`
  documenting what was generated, the validation results, and the full existing test-suite pass count.

## Explicitly Not In Scope (per requirements/execution plan)
- No API Layer, Repository Layer, Frontend, migration, or deployment-artifact changes — this unit has no
  such layers touched by this fix.
- No retroactive re-scan trigger (FR-6).
- No change to `similarity_threshold` / `recategorization_auto_apply_threshold` config values (FR-7).
