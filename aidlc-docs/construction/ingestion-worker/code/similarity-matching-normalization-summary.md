# Code Generation Summary — Similarity-Matching Normalization (WR-20)

## Files Modified
- `ingestion-worker/src/ingestion_worker/categorization/similarity.py`
  - Added `normalize_reference_noise(description: str) -> str`: two ordered regex passes (digit-run `\b\d{3,}\b`,
    short mixed-alphanumeric `\b(?=[A-Za-z0-9]{1,12}\b)(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+\b`),
    then whitespace collapse.
  - `find_best_match` now normalizes both `description` and each candidate's `description` before
    `fuzz.token_sort_ratio` (FR-4: both sides, every comparison). No signature change.
- `ingestion-worker/tests/test_similarity.py`
  - `TestNormalizeReferenceNoise` (7 tests): both noise-token shapes stripped, payee text and no-reference-code
    descriptions left unchanged, short digit-only tokens (e.g. `"7"` in `"7-ELEVEN"`) survive, decimal amounts
    in descriptions untouched, plus 2 Hypothesis property tests (never lengthens, idempotent) per this module's
    existing Partial-PBT convention.
  - `TestFindBestMatchReferenceCodeNoise` (4 tests): the 3 diagnosis examples re-run as same-payee
    repeat-payment pairs, all now matching at/above `similarity_threshold`; plus a cross-payee sanity check
    confirming unrelated payees still don't match (FR-3).

## No Other Files Changed
`categorization/service.py`'s call sites (`categorize`, `recategorize_unsure_from_precedent`) are unaffected —
both already just call `find_best_match`, which now normalizes internally. No API/Repository/Frontend/migration
changes (single-unit, single-component fix, per the approved execution plan).

## Verification
- `pytest tests/test_similarity.py -q`: 23/23 passed (12 pre-existing + 11 new).
- Full `pytest tests/ -q` (whole Ingestion Worker Service suite): **179/179 passed**, up from 168 — zero
  regressions, including the existing AXS false-positive amount-gate test and the CCY-conversion small-value
  test (both explicitly re-verified per NFR-2).
- Live diagnosis-example scores (via the actual `rapidfuzz` dependency, not assumed):
  - NEO EMPIRE repeat-payment pair: **100.0** (was 81.7 — the originally reported failure, now above the
    85.0 `similarity_threshold`)
  - WARBURG VENDING repeat-payment pair: **100.0**
  - CHANG WAI YEE repeat-payment pair (no reference-code noise to begin with): **100.0** (unaffected, as expected)
  - Cross-payee (CHANG WAI YEE vs. NEO EMPIRE): **46.96** — stays correctly far below threshold
