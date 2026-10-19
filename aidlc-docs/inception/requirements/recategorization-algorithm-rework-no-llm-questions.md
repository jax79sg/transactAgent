# Recategorization Algorithm Rework — "No LLM For Now" Follow-Up Questions

## Question 1
Reference-code/ID noise in descriptions was previously going to be caught by the LLM verification gate (that's why the earlier answer was "keep raw text, rely on the LLM instead of stripping IDs"). With the LLM gate deferred, should IDs now be stripped/scrubbed before embedding instead?

A) Yes — strip obviously ID-like substrings (long alphanumeric reference codes, transaction reference numbers) from the description before embedding, now that there's no LLM safety net to catch noise-driven false matches

B) No — keep the description raw and unmodified; rely purely on the broader precedent pool + tighter/recalibrated thresholds to compensate

C) Not sure — recommend whichever the evidence supports

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 2
Should the LLM verification gate (previously FR-RAR-2) be removed from the requirements document, or kept on record as an explicitly deferred future enhancement?

A) Remove it entirely — not in scope, don't document it as a future item

B) Keep it documented as deferred/future work — useful to have on record even though it's not being built now

C) Other (please describe after [Answer]: tag below)

[Answer]:B
