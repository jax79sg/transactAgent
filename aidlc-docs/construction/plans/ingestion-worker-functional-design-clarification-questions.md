# Unit 3 Functional Design — Clarification Questions

Two of your answers need a bit more precision before I can design the extraction/categorization pipeline.

## Clarification 1: LLM Provider Priority (from Question 1)
You said "prioritise free API calls from OpenRouter or a $10/month Gemini API key that I possess." Since your answer to Question 2 was **A) LLM-native document understanding** (send PDF pages directly to a vision-capable model), whichever model actually runs the extraction step must support vision/PDF input — not every free-tier model does.

### Clarification Question 1a — Primary Provider
Which should be the **primary** provider for both extraction (needs vision/PDF support) and categorization fallback (text-only is fine)?

A) **Google Gemini directly** (using your existing $10/month API key) — Gemini models have strong native PDF/vision support, simplest single-provider setup

B) **OpenRouter** as the primary gateway (giving access to many models, including free-tier ones, through one API) — requires picking a specific free-tier model on OpenRouter that supports PDF/vision input for extraction

C) **Hybrid**: Gemini (your paid key) for extraction specifically (since it needs reliable vision/PDF support), OpenRouter free-tier models for categorization fallback specifically (text-only, lower stakes, worth trying free first)

X) Other (please describe after [Answer]: tag below)

[Answer]: C

### Clarification Question 1b — Fallback Behavior
If the primary provider/model call fails (rate limit, outage, error), should the pipeline retry with a different provider, or just mark that statement/transaction as failed for this run?

A) **Fall back to the other provider** (whichever wasn't primary in 1a) before giving up — more resilient, more complexity

B) **No fallback provider** — if the primary call fails, mark the statement as failed (US-1.3 edge case) or the transaction as `UNSURE` (FR-5.2 step 4), and you can re-run ingestion later

X) Other (please describe after [Answer]: tag below)

[Answer]:B

## Clarification 2: Statement-Printed SGD Amount (from Question 5)
You noted statements often already show a converted-to-SGD amount printed on them. This changes how FR-10 (Currency Conversion) should work.

### Clarification Question 2a — Source Priority for Converted Amount
When a statement line shows both the original-currency amount AND an SGD-converted amount (as printed by the bank), which should be authoritative?

A) **Use the statement's printed SGD amount directly** as `converted_amount_sgd` whenever the extraction step finds one on the statement — this is the bank's own conversion (using their actual transaction-time rate), which is arguably more accurate than a public API's historical daily rate. Only fall back to a public FX-rate API when the statement does NOT print a converted amount (e.g., statements from banks/cards that don't show it).

B) **Always use a public FX-rate API** for consistency, ignoring any SGD amount the statement happens to print — simpler (one source of truth), but discards the bank's own (likely more accurate) conversion when available.

X) Other (please describe after [Answer]: tag below)

[Answer]:A

### Clarification Question 2b — Fallback FX API Provider
For transactions where the statement does NOT print a converted SGD amount (so a public API is still needed as fallback per 2a), which provider?

A) **Frankfurter** (frankfurter.app) — free, no API key required, ECB-sourced daily rates

B) **exchangerate.host** — free tier, no API key required

X) Other (please describe after [Answer]: tag below)

[Answer]:B

---

**Instructions**: Fill in each `[Answer]:` tag above, then let me know when you're done.
