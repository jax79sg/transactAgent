# Probable Duplicate Statement Detection — Requirements Clarification Questions

Please answer each question by filling in the letter choice after the `[Answer]:` tag. If none of the options match your needs, choose the last option (Other) and describe your preference. Let me know when you're done.

## What I found before drafting these (read-only look at your data, 2026-10-03)

**What exists today.** Duplicate prevention is a checksum of the PDF's raw bytes and nothing else. It reliably catches an *identical file* (it has: 3 of your Drive files were exact copies and were skipped). It cannot catch the *same statement saved as a different file*, and there is no transaction-level or period-overlap check anywhere in the worker.

**What it has missed in your data: two confirmed duplicate pairs, both June 2026.**

| Bank | Statements | Transactions | Period | Manual corrections |
|---|---|---|---|---|
| UOB | 2 files: `JUN 2026_20260728074739457.pdf` (ingested 4 Aug) and `JUN 2026_20260828174121571.pdf` (ingested 3 Sep) | 5 and 5, **all 5 identical** | 2 Jun to 30 Jun | 2 on the first copy, 0 on the second |
| Trust Bank | 2 statements | 8 and 8, **all 8 identical** | 2 Jun to 30 Jun | 0 on one copy, **2 on the other** |

Three things to notice. The file names contain what looks like a download timestamp, a month apart: the same statement was downloaded twice, so the bytes differ and the checksum was fooled. The Trust pair carries *different spellings of the bank name*, which is why my first check missed it, so any detection has to use the normalized bank key from the Account Balance work, not the raw name. And in both pairs **the manual corrections sit on only one copy**, so deleting the wrong copy would lose your work.

**A caution on small statements.** Two pairs of CIMB statements each share exactly 1 transaction (same date, description, amount) but each statement has only 1 transaction. That could be a duplicate, or it could be two different accounts that both received the same monthly interest. With so little to compare, transactions alone cannot tell.

**What the Account Balance work will add** (once its backfill has been run): each statement will carry an account identifier, a closing balance and date per account section. Same account plus same closing balance and date is a far stronger duplicate signal than matching transactions. Until the backfill runs, existing statements have no identifiers, so detection on existing data can only use bank plus transactions.

The Account Balance feature's Ingestion Worker code stage is still awaiting your approval; this new feature is separate from it.

## Question 1
When ingestion meets a file that looks like a duplicate of a statement you already have, what should happen to it?

A) Skip it automatically: do not ingest it, and record it in the run results as "probable duplicate of <statement>" with the reason, so you can see it and override.

B) Ingest it but hold it for review: its transactions are not counted in any dashboard, balance, or category learning until you confirm "keep" or "duplicate".

C) Ingest it normally and only warn: a notice in the run log and on the Review page, leaving the cleanup to you.

D) Other (please describe after [Answer]: tag below)

[Answer]: A. Possible to keep a record of top 10 transactions of this supposed duplicate and original so when ppl click on  "probable duplicate of <statement>", they are presented with this 10 transactions for human to be sure.

## Question 2
How alike must two statements be to count as a probable duplicate?

A) Strict: same bank, same account (when known), same period, and **every** transaction matches on date, amount, direction, and description. Catches both of your June pairs; misses a re-issued statement whose wording differs slightly.

B) Tolerant: same bank and period, and at least about 80% of the transactions match, allowing for the wording differences that can appear when the same PDF is read twice. Catches more; slightly higher chance of a false alarm.

C) Tolerant, and also partly overlapping periods (for example a statement re-issued with a shifted cycle).

D) Other (please describe after [Answer]: tag below)

[Answer]:B

## Question 3
Very small statements can match by coincidence (the CIMB example above: one transaction each, same date and amount). How cautious should detection be with them?

A) Do not treat a statement with fewer than 3 transactions as a duplicate on transactions alone; for those, require the account identifier and closing balance to match too (available after the Account Balance backfill).

B) Treat small statements like any other (a coincidence is flagged as a probable duplicate; nothing real is missed).

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 4
You already have two duplicate pairs (UOB June, Trust June), and others may be found later. How should existing duplicates be surfaced and cleaned up?

A) A list of probable duplicate pairs in the app (a panel on the existing Review page, with a notice badge like the other review flows), where you confirm which copy to remove. Nothing changes without your confirmation.

B) A command-line report only; I remove them myself with a command.

C) Remove them automatically, keeping the copy that carries your manual corrections (or the earlier one).

D) Other (please describe after [Answer]: tag below)

[Answer]: A

## Question 5
When a duplicate is confirmed, what does "remove" mean?

A) Delete the duplicate statement and its transactions permanently (the file in Drive is left alone). Simplest, but only a backup can undo it.

B) Mark it "duplicate, excluded" and keep it: ignored by dashboards, balances, exports, and category learning, but still visible and reversible.

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 6
In both of your pairs the manual corrections are on only one copy. Which copy should be kept as the original?

A) The one carrying manual corrections; if neither or both do, the earlier-ingested one.

B) Always the earlier-ingested one, with any manual corrections on the other copied across to the matching transactions first.

C) I choose each time.

D) Other (please describe after [Answer]: tag below)

[Answer]:A

## Question 7
The Account Balance backfill (once approved and run) re-reads every PDF and would recreate both duplicate pairs as they are. How should this feature relate to it?

A) Build this first, so the backfill's re-read applies the duplicate detection: probable duplicates are caught and reported during the backfill, and the two existing pairs are resolved as part of it.

B) Independent: the backfill goes ahead as already planned, and this feature cleans up duplicates afterwards.

C) Other (please describe after [Answer]: tag below)

[Answer]:A
