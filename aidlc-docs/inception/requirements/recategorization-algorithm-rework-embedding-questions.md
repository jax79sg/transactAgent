# Recategorization Algorithm Rework — Embedding Construction Follow-Up Questions

Your feedback about embedding construction is well-founded — `build_embedding_text` (`ingestion-worker/src/ingestion_worker/embedding/text.py:32`) currently just does `f"{description} | {price_bucket_label(amount)}"`: raw description text (including any reference-code noise) plus a price bucket. No in-flow/out-flow signal at all. This is a single shared function, though, used in three places:

1. The recategorization re-scan (in scope for this rework)
2. Ingestion-time `categorize()` (investigated and confirmed **not** currently showing the failure pattern — scoped out)
3. Recurring Payment Manager's own similarity matching (a separate feature entirely, not discussed yet)

Changing the shared function necessarily changes all three. A few questions to pin down how far this should reach:

## Question 1
Should the embedding-construction rework apply everywhere `build_embedding_text` is used, or just to the recategorization re-scan?

A) Apply everywhere — one shared function, one fix; ingestion-time categorization and recurring-payment matching should benefit too, not just the re-scan

B) Recategorization re-scan only — give the re-scan its own separate embedding-text construction, leave `categorize()` and Recurring Payment Manager exactly as they are today

C) Not sure — investigate whether ingestion-time categorization or recurring-payment matching would actually benefit (or risk regressing) from the same change before deciding

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 2
How should in-flow vs. out-flow factor into matching?

A) Append it as a signal inside the embedded text itself, similar to how the price-range bucket is already appended (e.g. `"... | $10 to $50 | outflow"`)

B) Use it as a hard pre-filter before similarity search even runs — never compare an inflow transaction against an outflow candidate at all — kept separate from the embedding text

C) Both — hard pre-filter AND include it as a signal in the embedded text

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 3
How should transaction IDs / reference codes be de-weighted?

A) Strip/scrub obviously ID-like substrings (long alphanumeric reference codes, transaction reference numbers) from the description before embedding, so they're never embedded at all

B) Keep the description raw and unmodified (preserves the existing "embed raw text" principle) and rely on the new LLM verification step to catch cases where embedding similarity was fooled by ID noise, rather than pre-processing text

C) Not sure — recommend whichever is more reliable based on the evidence

D) Other (please describe after [Answer]: tag below)

[Answer]:B
