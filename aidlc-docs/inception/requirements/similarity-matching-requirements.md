# Requirements: Similarity-Matching Normalization for Reference-Code Noise

Tracked as a Post-Completion change, same pattern as Epics 6/7/8. Base project status unchanged: COMPLETE.
This document is feature-scoped and does not modify the original project-wide `requirements.md`. On branch
`feature/recurring-payments-budget-alerts` (Epic 8 already complete on this branch, not yet merged to
`main`); this change is unrelated in scope to Epic 8 but touches the same `similarity.py` module Epic 8
partially reuses (`amounts_in_range` only — not `find_best_match`/`token_sort_ratio` scoring, which this
change targets).

## Intent Analysis

- **User Request** (paraphrased from conversation): User felt dining-category similarity matching was
  "too strict." Provided 3 real PayNow transaction examples. Diagnosis (confirmed live against the
  project's actual `rapidfuzz` dependency) found the three examples are correctly non-matching (different
  payees), but a **repeat payment to the same payee** scores only 81.7 — below the 85.0
  `similarity_threshold` — purely because each PayNow-style description embeds a unique, random
  per-transaction reference code (e.g. `OTHR-260102595543212111`, `OTHR-QR3 dy01qkET 00747`) inside the
  same string being fuzzy-scored. The amount-range gate is not implicated.
- **Request Type**: Bug Fix / Accuracy Enhancement to existing business logic (FR-5.2/WR-3, `business-rules.md`)
- **Scope Estimate**: Single Component — Categorization Engine (`ingestion-worker/src/ingestion_worker/categorization/`), primarily `similarity.py`; both existing call sites (`categorization/service.py`'s `categorize` and `recategorize_unsure_from_precedent`) are affected only via `find_best_match`'s internals, not their own signatures
- **Complexity Estimate**: Moderate — pure function change, but requires careful pattern design that must not regress the existing AXS PTE LTD false-positive protection (the reason `amounts_in_range` exists), and must stay generic rather than a one-off PayNow special-case

## Requirements Depth
**Standard** — clarified via one round of questions (`similarity-matching-questions.md`), all 6 answered
without requiring a follow-up clarification round (one apparent tension between answers, reconciled below
under Documented Assumptions #1 — flagged for the user to correct at the review gate if the reconciliation
is wrong).

## Functional Requirements

- **FR-1**: The system normalizes reference-code-shaped noise out of a transaction description before it
  is used in `find_best_match`'s fuzzy text-similarity scoring (`token_sort_ratio`), so that a repeat
  payment to the same payee is not blocked from matching purely because of a per-transaction reference
  code embedded in the description text.
- **FR-2**: Normalization is bank/payment-rail-agnostic — implemented as a general pattern recognizing
  reference-code-shaped tokens (e.g. runs of 3+ consecutive digits, short alphanumeric tokens that mix
  letters and digits), not hardcoded to literally check for "PayNow" or a specific bank name — so other
  banks'/rails' equivalent embedded reference noise also benefits, without a bank-specific carve-out.
  Concretely, normalization must be sufficient that a repeat payment to the same payee (same payee text,
  different reference code) scores at or above `similarity_threshold` for all 3 diagnosis examples used
  as regression cases, given amounts already in range.
- **FR-3**: Normalization is conservative — it strips only clearly reference-code-shaped tokens and must
  NOT alter payee/merchant name text or other legitimate content. It must not, on its own, cause two
  genuinely different payees to fuzzy-match as the same — the amount-range gate (`amounts_in_range`)
  remains the primary defense against that (unchanged, out of scope — see below).
- **FR-4**: Normalization is applied to BOTH sides of every text-similarity comparison performed by
  `find_best_match` — the incoming/live description and every historical candidate description (from
  `list_similarity_candidates` and from the recategorization precedent flow) — before scoring. Normalizing
  only one side would not fix the diagnosed repeat-payment case.
- **FR-5**: This is a new, standalone normalization function scoped to `categorization/similarity.py`'s
  matching path only. It is NOT merged or shared with the existing private `_normalize_description` in
  `recurring_payments/service.py`, which serves a different purpose (exact-match clustering for
  cadence detection, WR-19) and is left unchanged.
- **FR-6**: This fix applies going forward only. No retroactive re-scan of existing `UNSURE` or
  already-categorized transactions is triggered as part of this change. The existing FR-5.4/WR-5/WR-9/WR-10
  recategorization mechanisms are unchanged in behavior beyond automatically benefiting from the new
  normalization the next time they run.
- **FR-7**: `similarity_threshold` (85.0) and `recategorization_auto_apply_threshold` (97.0) are unchanged
  by this fix. The fix's goal is exclusively to stop reference noise from artificially depressing a score
  that should already clear the existing bar — not to lower the bar itself.

## Non-Functional Requirements

- **NFR-1**: Remains a pure function (no DB/IO), consistent with this module's existing Partial
  property-based-testing adoption (`aidlc-state.md` Extension Configuration: PBT "Partial — pure
  functions / serialization round-trips only") — should receive property-based test coverage alongside
  example-based tests, consistent with the existing `test_similarity.py` precedent.
- **NFR-2**: Must not regress the existing false-positive protection the amount-range gate provides (the
  AXS PTE LTD incident it exists for) — existing `similarity.py` tests must continue to pass unchanged,
  and the AXS-style scenario (near-identical text, very different amounts) must still correctly not match.
- **NFR-3**: Normalization must remain a cheap, allocation-light string operation — it runs on every
  candidate comparison in `find_best_match`'s scan, so it must not introduce a material performance
  regression (e.g. no per-candidate DB/network calls, no unbounded-cost pattern matching).

## Business Context

- **Goal**: Improve categorization-matching accuracy for small, low-value PayNow-style payments —
  disproportionately dining-related in Singapore — without weakening the AXS-incident-driven false-positive
  protection that the amount-range gate provides.
- **Success Criteria**: All 3 diagnosis examples, when re-run as same-payee repeat-payment pairs (same
  payee, different reference code, amount in range), score at or above `similarity_threshold`. Existing
  similarity-matching test suite (including the amount-gate regression protection) continues to pass
  unchanged.

## Documented Assumptions (flagged, not further questioned)

1. **Reconciling Q1 (B — general, bank-agnostic heuristic) with Q5 (A — conservative, only
   clearly-reference-code-shaped tokens)**: these two answers are read together, not in conflict — "general"
   describes *applicability* (the pattern isn't hardcoded to the literal string "PayNow" or a specific
   bank name, so other rails benefit too), while "conservative" describes *aggressiveness* (the pattern
   only strips tokens that are themselves clearly reference-code-shaped — digit runs, short
   alphanumeric-with-digit tokens — and leaves payee names and everything else untouched). FR-2 and FR-3
   above encode this reconciliation. **Flagged explicitly for correction at the review gate if this
   reading is wrong.**
2. The exact pattern/regex implementing FR-2/FR-3 (including how to handle the trailing period in
   `OTHR-260102595543212111.` and the spaced hyphen in `OTHR - OTHR`) is deferred to Functional Design,
   validated against the three diagnosis examples as concrete test cases.
3. No new user-facing config/settings value is introduced for this fix — unlike `similarity_threshold`,
   this normalization isn't intended to be user-tunable. Can be revisited later if needed.

## Out of Scope

- Retroactive re-scan of historical `UNSURE`/already-categorized transactions (FR-6).
- Any change to `similarity_threshold` or `recategorization_auto_apply_threshold` (FR-7).
- Consolidating with `recurring_payments/service.py`'s `_normalize_description` (FR-5).
- Any change to the amount-range gate (`amounts_in_range`) — unaffected by this change.
- Any Database, API Service, or Frontend SPA changes — this is entirely internal to the Ingestion Worker
  Service's Categorization Engine component.
