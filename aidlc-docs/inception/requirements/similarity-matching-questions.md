# Similarity-Matching Refinement — Clarifying Questions

Context: `find_best_match` (`ingestion-worker/src/ingestion_worker/categorization/similarity.py`) scores
two transaction descriptions with `rapidfuzz.fuzz.token_sort_ratio` against a fixed threshold
(`similarity_threshold = 85.0`). Diagnosed root cause: PayNow-style descriptions (dominant payment
method for small/dining purchases in Singapore) embed a unique, random per-transaction reference code
(e.g. `OTHR-260102595543212111`, `OTHR-QR3 dy01qkET 00747`) inside the same description string that gets
scored — so even a repeat payment to the exact same payee can score below threshold purely from that
noise, which is what's making dining-category matching feel too strict. The amount gate
(`amounts_in_range`) is not implicated.

Please answer by filling in the letter after each `[Answer]:` tag.

## Question 1
What should the fix normalize away before scoring?

A) Only PayNow-shaped reference codes specifically — text matching known patterns like `OTHR-<digits>`, `OTHR - OTHR`, `QR<code>` (narrowest, lowest false-positive risk, but may miss other banks'/rails' equivalent noise, e.g. cheque numbers, POS terminal IDs, other transfer types)

B) A general "trailing/embedded reference-code-shaped noise" heuristic not tied to PayNow specifically — e.g. long digit runs, short alphanumeric-with-digit tokens — so any bank/rail with similar embedded-reference noise benefits, not just PayNow

C) Reuse and generalize the existing `_normalize_description` in `recurring_payments/service.py` (currently only strips a trailing `#123`-style number for its own cadence-detection clustering) into one shared normalization utility used by both call sites, extended to also cover the PayNow noise shapes from the examples

D) Other (please describe after [Answer]: tag below)

[Answer]: B

## Question 2
The existing `recurring_payments/service.py` already has its own private, narrower normalization
function for a different purpose (grouping identical merchants for recurring-cadence detection). Should
this fix's normalization logic be:

A) A brand new, separate function scoped only to `categorization/similarity.py`'s `find_best_match` — keeps the two features fully independent, no shared-code risk between them

B) Consolidated into one shared, public normalization utility that both `similarity.py`'s matching and `recurring_payments/service.py`'s clustering call — avoids two divergent implementations of "what counts as noise in a transaction description" drifting apart over time

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 3
Should normalization apply to descriptions on both sides of every comparison (the incoming transaction
being categorized/re-scanned AND every historical candidate pulled from
`list_similarity_candidates`/the recategorization precedent), or only one side?

A) Both sides — normalize before every scoring comparison, regardless of which description is "new" vs "historical" (most consistent; matches how the bug reproduces — normalizing only one side wouldn't have fixed the NEO EMPIRE repeat-payment case)

B) Only the incoming/new transaction's description — leave historical candidate text as-is

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 4
Should this fix be applied retroactively to transactions already sitting in `UNSURE` or already
categorized (re-running the FR-5.4/WR-5/WR-9/WR-10 recategorization-style scan with the new normalization
logic), or only affect matching going forward for newly-ingested transactions and new manual corrections?

A) Forward-only — no retroactive re-scan; only new ingestion/re-categorization events benefit from the improved matching

B) Also trigger one retroactive scan of existing `UNSURE` transactions (and let already-categorized transactions surface as review proposals, same as the existing WR-9/WR-10 broadened re-scan does today) so the fix's benefit isn't limited to future data

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 5
The amount-range gate (`amounts_in_range`) exists specifically because of a real prior incident (AXS PTE
LTD — near-identical text, wildly different amounts, wrongly suggested as a match). Stripping more text
as "noise" narrows what differentiates two descriptions, which could in theory make it easier for two
genuinely different low-amount PayNow payments to look alike. Given the amount gate already limits this
(anything within the $5 floor or 4x ratio), how cautious should the normalization be?

A) Conservative — only strip clearly reference-code-shaped tokens (the `OTHR-...`/`QR...` patterns from the diagnosis); leave payee names and everything else untouched, minimizing any chance of collapsing two real payees together

B) Accept a slightly broader heuristic (per Question 1's answer) since the amount gate is already the primary defense against unrelated-transaction false positives, and text noise alone rarely makes two different payee names collide

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 6
Is a change to the `similarity_threshold` value itself (currently 85.0) in scope for this change, or is
normalizing the noise out before scoring intended to be the complete fix?

A) Normalization only — do not touch `similarity_threshold` (or the separate `recategorization_auto_apply_threshold`); the goal is to stop noise from artificially lowering scores that should already clear the bar, not to make the bar itself lower

B) Also open to revisiting the threshold value as part of this change if testing shows normalization alone isn't sufficient

C) Other (please describe after [Answer]: tag below)
[Answer]: A

[Answer]:
