# Account Balance at a Point in Time — Clarifying Questions

Investigated the current data model and live production data before drafting these. Two real gaps turned up that directly shape what this feature can actually deliver, so please read the context under Questions 1 and 2 carefully before answering.

## Question 1
**Context**: There is no "Account" entity in the system today — only a free-text `bank_name` field captured per statement/transaction, extracted straight from each PDF's own header. Checking the live data, this has already fragmented into 15 raw values that clearly represent far fewer real accounts, e.g.:
- `OCBC` / `OCBC Bank`
- `DBS` / `POSB` / `DBS / POSB`
- `Trust` / `Trust Bank` / `Trust Bank Singapore Limited`
- `CIMB BANK` / `CIMB Bank`

A "balance per account" feature needs a real answer to "what counts as one account" before it can group transactions correctly.

How should account identity be resolved?

A) Introduce a proper `Account` entity now. I'll tell you my real list of accounts, and every bank-statement ingestion (past and future) gets mapped to one of them — most correct, but the most work, and needs a one-time manual mapping of existing statements.

B) Canonicalize the existing raw `bank_name` values into a fixed set (e.g. merge the `OCBC`/`OCBC Bank` variants) without a new `Account` entity — simpler, but can't distinguish two real accounts at the same bank if you have any.

C) Treat each distinct raw `bank_name` string as its own account for now, exactly as stored today — no data cleanup, but the balance view will show the same real-world account split into multiple rows (e.g. `Trust` and `Trust Bank` shown separately).

D) Other (please describe after [Answer]: tag below)

[Answer]:A. I am willing to reingest all the bank statements again. Balances should be limited to Savings accounts only, not credit accounts.

## Question 2
**Context**: More fundamental — no absolute balance has ever been captured anywhere in this system. The PDF extraction step *deliberately discards* every "opening balance" / "closing balance" / "balance brought forward" line specifically to avoid double-counting them as transactions (see `ingestion-worker/src/ingestion_worker/extraction/prompts.py`). So there is no anchor point anywhere to reconstruct a real bank balance from — only the running sum of inflow/outflow transactions we've ingested.

How should "balance" be computed given that?

A) Purely relative: sum(inflow − outflow) from the earliest ingested transaction up to the requested date, clearly labeled as "net change since records began" — will NOT match your real bank balance unless the account had exactly $0 the moment your very first ingested transaction happened.

B) I'll supply a real known balance as of a specific date once per account (e.g. from a recent statement or online banking) as a manual anchor; the feature computes forward/backward from that anchor using the transaction sum. Dates before the anchor use the relative estimate from (A) unless I supply more anchors.

C) Start capturing the closing-balance line that's already printed on every statement (currently thrown away) as a stored per-statement anchor going forward, and use the nearest prior anchor for any requested date. Note: this only starts working going forward — historical dates before this ships still fall back to (A) or (B) unless combined with one of those.

D) Other (please describe after [Answer]: tag below)

[Answer]: Answered in Question 2, i am willing to reingest all statements.

## Question 3
What granularity should "a particular time" support?

A) An exact calendar date only (balance as of end-of-day on that date)

B) A month/period picker only (balance as of the end of the selected month)

C) Both — exact date and a month shortcut

D) Other (please describe after [Answer]: tag below)

[Answer]: C

## Question 4
Should this show per-account balances only, or also a combined total across all accounts?

A) Per-account only

B) Per-account plus an all-accounts-combined total

C) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 5
Is a single point-in-time lookup the whole feature, or should it also show a balance trend/history (e.g. a chart of balance over time, not just one date's value)?

A) Single point-in-time lookup only

B) Point-in-time lookup plus a balance-over-time chart/trend view

C) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 6
Where should this live in the app?

A) A new dedicated page

B) Added to the existing Dashboard page

C) Added to the existing Transactions page

D) Other (please describe after [Answer]: tag below)

[Answer]:B
