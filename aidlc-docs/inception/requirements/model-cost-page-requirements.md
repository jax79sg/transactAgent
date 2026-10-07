# Requirements — Model Cost Page (GitHub issue #28, 2026-10-07)

**Request (issue #28, jax79sg):** "Have a page to show the total costs associate with model calls via gemini or any cloud resource you used. Granularity should be at date level and allow some form of group so users can see how much they spent."
**Depth:** Standard (a new table, a recording step in four call sites, one API endpoint, one page). **Branch:** `feature/issue-28-model-cost-page`.

## Findings
- The app calls a paid cloud model in four places: statement extraction (worker, Gemini through `google-genai`), categorisation (worker, Gemini through its OpenAI-compatible endpoint when `categorization_provider` = gemini), embeddings (worker, same endpoint when `embedding_provider` = gemini) and Ask AI (API, `google-genai`). Nothing recorded what any of them used.
- What each call reports (probed live 2026-10-07 with one-word prompts): `google-genai` returns `usage_metadata` (prompt, candidates and, for thinking models, thoughts token counts); the chat endpoint returns `usage` (prompt and completion tokens); **the embeddings endpoint returns no usage at all**, so those tokens have to be estimated.
- Google's price list (checked 2026-10-07): gemini-3.5-flash-lite $0.30 per million input tokens (text, image, video and audio alike) and $2.50 per million output tokens (thinking included); gemini-embedding-2 $0.20 per million input tokens.
- The app's other outside services cost nothing: Google Drive (free API quota), the exchange-rate service (free), Qdrant and PostgreSQL (local). Local model servers are the user's own hardware. So "any cloud resource" is today exactly the four Gemini call sites.
- Spend before this change was never recorded and cannot be recovered; the page starts empty at deployment.

## Requirements
- **MC-1** Every successful call to a paid cloud model records one usage row: when, purpose (`statement_extraction`, `categorization`, `embedding`, `ask_ai`), provider (`gemini`), model, input tokens, output tokens (thinking tokens count as output, as Google bills them), whether the tokens were estimated, and the cost in USD.
- **MC-2** The cost is worked out when the call is made, from the token counts and three prices kept in Settings (per million tokens: Gemini input, Gemini output, Gemini embedding; defaults from the price list above), and stored with the row, so changing a price later does not rewrite history. Token counts are stored too, so a cost can be recomputed.
- **MC-3** Embedding tokens are estimated (one token per four characters, rounded up, at least one) and the row says so; the page says so wherever estimated rows are in the range.
- **MC-4** Recording never breaks or noticeably slows a model call: it runs in its own short transaction right after the response arrives (so a later failure of the caller's own transaction cannot erase money already spent), and any failure to record is logged and swallowed.
- **MC-5** Calls to the local provider are not recorded (no cloud cost); a request that fails is not recorded (Google does not bill it).
- **MC-6** A **Costs** page (new nav link) shows, for a date range (default the last 30 days): total cost, calls and tokens; a chart and a table by period with granularity **day / week / month**; and a **group by** choice — nothing, purpose, or model — that splits the chart and adds a totals-per-group table. Days are the user's own calendar days (the browser's time zone is sent), weeks start on Monday.
- **MC-7** Every table on the page sorts on every column (issue #23's rule). Money is shown in USD (what Google bills), never mixed with the app's SGD figures.
- **MC-8** The three prices appear in Settings (category "Model Costs", advanced) with the price-list source named.

## Out of scope (stated, not forgotten)
- Back-filling spend from before this change; budgets or alerts; exporting; per-statement or per-transaction cost attribution; recording local-model calls; model-training's local calls.

## Assumptions made without asking (revisit in review)
1. USD, not SGD (the bill's currency; no FX guesswork).
2. Only paid cloud calls are recorded.
3. Three flat prices rather than a per-model price table: if the Gemini model is changed in Settings, the prices should be changed with it (the Settings text says so).
