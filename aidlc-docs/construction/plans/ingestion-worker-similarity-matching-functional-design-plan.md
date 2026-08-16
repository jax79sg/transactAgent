# Functional Design Plan — Ingestion Worker Service: Similarity-Matching Normalization

Unit: Ingestion Worker Service (Categorization Engine component only). No other unit affected.

## Context
Requirements FR-1..FR-7 (`similarity-matching-requirements.md`) specify *what* the normalization must do.
Documented Assumption #2 in that doc explicitly defers the exact pattern/regex to this stage, to be
validated against the 3 diagnosis examples as concrete test cases. That validation is done below — no
open ambiguity remains that requires a user question, so no `[Answer]:` tags are used in this plan.

## Step 1: Analyze Unit Context
- [x] Re-read `categorization/similarity.py` (current `find_best_match`, `amounts_in_range`) — confirmed
  amount gate filters candidates *before* text scoring, so it stays the primary defense independent of any
  text-normalization change (relevant to NFR-2).
- [x] Re-read `categorization/service.py` call sites (`categorize`, `recategorize_unsure_from_precedent`) —
  confirmed neither passes anything that would need signature changes; both just call `find_best_match`.
- [x] Re-read existing `test_similarity.py` / `test_categorization_service.py` regression tests (AXS,
  CCY-conversion small-value) to confirm the new normalization cannot regress them.

## Step 2: Design the Normalization Pattern
- [x] **Digit-run pass**: strip whole word-bounded tokens of 3+ consecutive digits (`\b\d{3,}\b`) — covers
  `260102595543212111`, `00747`, and the AXS/precedent reference numbers.
- [x] **Short mixed-alphanumeric pass**: strip whole word-bounded tokens that are 1–12 characters AND
  contain at least one letter AND at least one digit — covers `QR3`, `dy01qkET`. The 12-char bound is a new
  design parameter (not specified in requirements); chosen generously above the longest real example
  (`dy01qkET`, 8 chars) with headroom for other rails, while still being clearly "short" per FR-3's
  conservative intent.
- [x] Collapse resulting whitespace runs and strip leading/trailing whitespace. Deliberately do NOT strip
  leftover punctuation (e.g. a dangling `-` or `.` where a token was removed) — it's cosmetic, appears
  symmetrically on both sides of any comparison (same template, same removal), and removing it would add a
  third regex pass beyond what FR-2 specifies for no matching-accuracy benefit.
- [x] Deliberately leave literal `OTHR` untouched — it's a fixed, non-varying rail marker, not
  per-transaction noise; stripping it would be scope creep beyond FR-2/FR-3.
- [x] **Validated live** (actual `rapidfuzz.fuzz.token_sort_ratio`, not assumed) against all 3 diagnosis
  examples as same-payee repeat-payment pairs (different reference/QR code, amount held in range):
  - NEO EMPIRE pair: 100.0 (was 81.7, the originally reported failure)
  - WARBURG VENDING pair: 100.0
  - Cross-payee sanity check (CHANG WAI YEE vs NEO EMPIRE, unrelated): 46.96 — stays correctly far apart
- [x] **Validated no regression** against the existing AXS false-positive test: normalized AXS descriptions
  score 100.0 (up from 98.57) — but `test_same_merchant_wildly_different_amount_does_not_match` still passes
  because the amount gate ($699 vs $81.70) rejects the candidate *before* text scoring runs at all (Step 1
  finding); a higher text score cannot resurrect a candidate the amount gate already excluded.
- [x] **Validated no regression** against the CCY-conversion small-value test (`1.48 SGD` / `26.86 SGD`) —
  decimal amounts embedded in description text are 2-digit runs each side of the point, below the 3-digit
  threshold, so untouched; score unchanged behavior.

## Step 3: Known, Accepted Limitation (documented, not a new open question)
- [x] A genuine merchant/payee name that is itself a short letter+digit token (e.g. a hypothetical `3M`)
  would be stripped by the short-mixed-alphanumeric pass. This is an explicit, requirements-approved
  trade-off (FR-2's literal heuristic), not a new design gap — documented in the business-rules addendum
  for transparency rather than silently accepted.

## Step 4: Generate Functional Design Artifacts
- [x] `business-rules.md` — add **WR-20** documenting the normalization rule, both regex passes, the
  applies-to-both-sides requirement (FR-4), and the known limitation from Step 3.
- [x] `business-logic-model.md` — add a short addendum to the Categorization Engine section describing
  where `normalize_reference_noise` sits in the `find_best_match` flow.
- [x] `domain-entities.md` — **no change**. No new/modified entity; this is pure function-internal logic.

## Step 5: Present Completion Message
- [x] Present standard 2-option completion message, wait for explicit approval before Code Generation.
