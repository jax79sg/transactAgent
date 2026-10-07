# Summary — Model Cost Page (GitHub issue #28, 2026-10-07)

**Request:** "Have a page to show the total costs associate with model calls via gemini or any cloud resource you used. Granularity should be at date level and allow some form of group so users can see how much they spent."
**Requirements / plan:** `inception/requirements/model-cost-page-requirements.md`, `construction/plans/model-cost-page-code-generation-plan.md`. **Branch:** `feature/issue-28-model-cost-page`. **Not deployed** (see the end).

## What was built
- **A ledger.** `model_usage` (migration 0021, additive, refuses to downgrade while it holds rows): one row per successful paid Gemini call — when, purpose, provider, model, input and output tokens, whether the tokens are estimated, cost in USD (8 decimals; an embedding call costs a few millionths of a dollar).
- **Recording at the four call sites** (`transactagent_db/model_usage.py` holds the arithmetic and the never-fail rule; each service has a thin `usage.py`): statement extraction, categorisation (single and batch, Gemini provider only), embeddings (Gemini provider only; tokens estimated at four characters each because Google's embeddings endpoint reports none, and flagged so), Ask AI. Recorded right after the response arrives, in its own transaction, so a later rollback cannot erase spend and a recording failure is logged and swallowed, never breaking the call. Local-provider calls and failed calls are not recorded.
- **Three prices in Settings** ("Model Costs", advanced): Gemini input, output and embedding per million tokens, defaulting to Google's published $0.30 / $2.50 / $0.20 (checked 2026-10-07 for gemini-3.5-flash-lite and gemini-embedding-2). The cost is worked out when the call is made and stored.
- **`GET /costs`**: date range, granularity day / week (Monday start) / month, group by none / purpose / model, the viewer's time zone (so a day is the viewer's calendar day). Returns totals, every period in the range (zero-filled), the series and per-group totals.
- **The Costs page** (new nav link between Review and Settings): summary tiles, a stacked bar chart (the app's validated palette, fixed colour per purpose, legend, 2 px surface gaps, dollar axis and tooltips with a per-day total), a period table and a group table, both sortable on every column, a note that embedding costs are estimates, an explanatory empty state, and phone-width layout.

## Findings worth keeping
- Google's chat and native APIs report exact token counts; the embeddings endpoint reports none (probed live) — hence the estimate flag.
- `gemini-3.5-flash-lite` does no hidden thinking by default (native and compatible endpoints agree to the token); thinking tokens are still counted as output if a response ever includes them.
- A constant (`'All'`) in `ORDER BY` is rejected by Postgres, so "group by nothing" selects the constant but never groups or orders on it.
- A mistake in the month-stepping arithmetic made the period list loop forever (found by a mutation check, which is why that check carries a timeout); the correct arithmetic is covered by a year-rollover test.

## Verification
- Suites: database 239, ingestion worker 734, API 424, frontend 270 — all pass; `ruff` clean in the three Python services; `tsc` clean; `eslint` 0 errors (the 5 warnings are older).
- **72 mutation checks, all caught** (38 Python, 34 frontend; one by timeout). Four tests were strengthened because mutations survived at first: thinking tokens counted on their own, sort tie-break, the local-date default range, the viewer's time zone being sent.
- Migration 0021 applied from scratch and downgraded/re-upgraded on a scratch Postgres; the downgrade refuses with rows present.
- **Real calls:** this branch's clients were run inside the worker container (which holds the Gemini key) against a *scratch* database: an embedding (13 estimated tokens, $0.00000260), a categorisation (68 in / 2 out, $0.00002540) and an extraction with an image (1,098 in / 1 out, $0.00033190) each left exactly one correctly priced row.
- **In the browser** (scratch API and database with 708 sample rows, built frontend): the page, grouping by purpose and model, week and day granularity, the tooltip, and the phone layout (no page-level horizontal scroll; tables scroll inside their frames).

## Decisions left to the user
1. **Deploying.** The live stack still runs the merged `main`; this branch needs the API, worker and frontend rebuilt and migration 0021 applied. Spend before deployment was never recorded and cannot be recovered.
2. **USD, not SGD**, and **only paid cloud calls** are recorded (assumptions in the requirements).
3. **Flat prices, not a per-model table**: change the prices when the Gemini model is changed.
