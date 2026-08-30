# Recategorization Algorithm Rework — Clarification Questions

Before proposing a rework, here's what the evidence already shows, so you can correct me if I'm reading it wrong:

- The "recategorization scan" is the retroactive re-scan (`recategorize_unsure_from_precedent` — triggered when you manually correct a transaction's category, it looks for other UNSURE transactions similar to the one you just fixed and either auto-applies the same category or proposes it for review).
- Querying the live `recategorization_jobs`/`recategorization_proposals` tables: from **2026-08-23 through 2026-08-27, every single proposal batch was rejected** (~9 jobs, 100% reject rate). Compare to 2026-08-15–08-18, which had a healthy mix of approved/rejected/auto-applied. Something got noticeably worse around 08-23.
- `.env` currently overrides `EMBEDDING_SIMILARITY_THRESHOLD=0.75`, looser than the code's own default of `0.82` — this lowers the bar for a candidate to even be considered, which could be feeding in weaker matches.
- Today's runs (post the LLM model swap) all show `updated_transaction_count=0` with proposals stuck at "pending" — too recent/too few to tell if that's the same problem or something new.

Please answer the questions below.

## Question 1
When you say "total failure," what's actually going wrong when you review a recategorization proposal?

A) The proposed category is just plain wrong / unrelated to the transaction (bad matches getting surfaced at all)

B) The category is plausible-ish but not what you'd have picked — too eager to guess instead of leaving it UNSURE

C) It's missing obviously-similar transactions that should have matched and didn't (too conservative, not too aggressive)

D) Auto-applied changes (not just proposals) are wrong, and you're having to manually undo them

E) Other (please describe after [Answer]: tag below)

[Answer]: A and C

## Question 2
Is this only about the retroactive re-scan (triggered by correcting one transaction, scans existing UNSURE transactions), or does the rework need to also cover the initial ingestion-time categorization (`categorize()` — the embedding + fuzzy-match + LLM fallback chain new transactions go through when first imported)?

A) Retroactive re-scan only — ingestion-time categorization is fine as-is

B) Both — the same underlying similarity-matching approach is the problem everywhere it's used

C) Not sure — investigate whether ingestion-time categorization shows the same failure pattern before deciding scope

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 3
The re-scan currently only ever compares UNSURE transactions against the *one* transaction you just corrected (a single pairwise comparison), not against your full history of past corrections for that category. Is broadening what it compares against part of what "rework the algorithm" means to you?

A) Yes — it should learn from all your past corrections/precedents for a category, not just the most recent single one

B) No — comparing against just the one just-corrected transaction is fine; the matching logic itself (thresholds, embedding vs. fuzzy-text, scoring) is what needs fixing

C) Not sure — open to whichever approach actually fixes the false-positive rate

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 4
Right now a match either auto-applies (score ≥ 97) or becomes a pending proposal you review (score ≥ threshold but < 97) — never involves an LLM call (by design, WR-5, to keep the re-scan cheap/fast). Should the reworked algorithm involve an LLM check, given the near-100% reject rate suggests pure similarity scoring isn't reliable enough on its own?

A) Yes — add an LLM confirmation step, even if it's slower/costs more, since correctness matters more than speed here

B) No — keep it LLM-free; fix it by tuning/replacing the similarity scoring itself (thresholds, embedding model, scoring formula)

C) Not sure — recommend whichever approach best fixes the false-positive rate, cost/speed is secondary

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 5
Should investigating *why* it broke around 2026-08-23 (e.g. the looser `.env` threshold, a data pattern in recently-ingested statements, or something else) come before designing the rework — since a config fix might resolve much of this without an algorithm rewrite at all — or do you already want to move straight to a redesign regardless of root cause?

A) Investigate root cause first — if it's a tunable/config problem, fix that before touching the algorithm's design

B) Skip investigation — go straight to a rework; the current approach needs replacing regardless of what caused this specific regression

C) Do both — quick root-cause check in parallel, but proceed with rework planning either way

D) Other (please describe after [Answer]: tag below)

[Answer]:C

## Question 6
How much manual review should the reworked algorithm still require? (Shapes whether we lean toward higher-confidence-only auto-apply, more proposals for your review, or something more automated.)

A) Minimize false positives even if it means fewer auto-applies and more transactions staying UNSURE — I'd rather review less garbage

B) Minimize manual review burden — auto-apply more aggressively, even if that means occasionally getting one wrong

C) Keep the current balance of auto-apply vs. pending-review, just make the matching itself more accurate

D) Other (please describe after [Answer]: tag below)

[Answer]:A
