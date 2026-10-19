# Probable Duplicate Statement Detection — Clarification Question

Thanks. Six of your seven answers are clear and settled:

| # | You chose | What it means |
|---|---|---|
| 1 | A, plus an addition | Skip a probable duplicate automatically and record it in the run results as "probable duplicate of <statement>", with the reason, so you can see it and override. **Plus**: keep a record of the top 10 transactions of both the suspected duplicate and the original, so that clicking "probable duplicate of <statement>" shows them and a person can be sure. |
| 2 | B | Same bank and period, and about 80% or more of the transactions match, tolerating small wording differences. |
| 3 | A | A statement with fewer than 3 transactions is never treated as a duplicate on transactions alone; it also needs the account identifier and closing balance to match (so this applies once the Account Balance backfill has run). |
| 4 | A | Existing duplicates appear as a list in the app (a panel and badge on the Review page) where you confirm which copy to remove; nothing changes without your confirmation. |
| 5 | A | Removing a confirmed duplicate deletes that statement and its transactions permanently (the file in Drive is left alone). |
| 6 | A | Keep the copy carrying manual corrections; if neither or both do, keep the earlier-ingested one. |
| 7 | A | Build this before the Account Balance backfill, so the backfill's re-read applies the detection and the two existing pairs are resolved as part of it. |

**Your question: is it possible to keep a record of the top 10 transactions?** Yes. A skipped duplicate is never ingested, so its transactions would not exist anywhere in the database; the detection step would store a small snapshot (up to 10 transactions from each side) together with the "probable duplicate of <statement>" record, and the app would show it when you click. It costs very little storage.

## One thing I need from you: which 10?

"Top 10" can mean two different things, and it changes what you would see when deciding whether it really is a duplicate.

### Clarification Question 1
Which 10 transactions should be shown on each side?

A) The **10 largest by amount** on each statement (ties: earlier date first), with each row marked "also on the other statement" or "only on this one". Large transactions are the easiest to recognise, and the markers show both what matches and what does not.

B) The **first 10 by date** on each statement (the top of the statement as printed), with the same "also on the other statement" / "only on this one" markers.

C) Other (please describe after [Answer]: tag below)

[Answer]:A
