# Account Balance at a Point in Time — Clarification Questions

Thanks for the answers. Q3–Q6 are clear and settled: exact date plus a month shortcut (Q3), per-account balances plus a combined total (Q4), point-in-time lookup plus a balance-over-time chart (Q5), added to the existing Dashboard page (Q6). Q1 is settled as option A (a real `Account` entity, full reingest accepted).

A few things your answers left open, plus one risk the "reingest" answer didn't cover, need resolving before I write the requirements document.

## Ambiguity 1: Which option did Question 2 intend?
Your Q2 answer was "Answered in Question 2, i am willing to reingest all statements" — it sits inside Question 2 and names no option, so I can't tell which of the three approaches you meant. "Willing to reingest" most plausibly points at option C (capture each statement's printed closing balance), but I don't want to assume.

Investigated: the extraction schema (`ingestion-worker/src/ingestion_worker/extraction/schemas.py`) and the `BankStatement` model currently capture no balance of any kind, so whichever option you pick needs new extraction.

### Clarification Question 1
How should a balance be computed?

A) Capture each statement's printed closing balance as a stored per-statement anchor (reingest backfills all history). For any requested date, use the nearest prior closing balance plus the transactions after it up to that date.

B) A manual anchor: I supply one known real balance per account (as of a specific date) and the feature computes forward and backward from it using the transaction sum. Reingesting is irrelevant to the balance in this case.

C) Both: capture statement closing balances automatically, and also allow a manual per-account override anchor for any account where a statement's balance can't be read reliably.

D) Other (please describe after [Answer]: tag below)

[Answer]: C. Use capture statement closing balance as a cross checking measure to your manual anchor.

## Gap 1: How is the real account list established?
Q1 = A needs "my real list of accounts", but none was supplied. Investigated: statements currently carry only a free-text `bank_name`. The extraction step does not read any account number or account identifier, so there is currently nothing on a statement to match to a specific account if you have two accounts at the same bank.

### Clarification Question 2
How should accounts be created and matched to statements?

A) Auto-create an `Account` from each statement's header at ingestion — bank name plus the account number (or its last few digits) newly extracted from the PDF — with a way in the UI for me to rename or merge accounts afterwards.

B) I'll provide the full list of my accounts below (bank, nickname, and a distinguishing identifier such as the last 4 digits), and every statement is matched against that fixed list; anything that doesn't match is flagged for review.

C) Other (please describe after [Answer]: tag below)

[Answer]: A

## Gap 2: How is "Savings only" determined?
Your Q1 answer limits balances to savings accounts, not credit accounts. Investigated: the extraction prompt reads both "bank or credit card" statements indiscriminately and records no account type, so today nothing distinguishes the two. I'm assuming credit-card statements continue to be ingested exactly as today (for spending and categories) and are only excluded from the balance view — tell me under "Other" if that's wrong.

### Clarification Question 3
How should savings vs credit be determined?

A) Extend extraction to read the account type from the statement itself (savings/current vs credit card) and exclude credit-card accounts from balances automatically.

B) Set it once per account — when I confirm or create each `Account` (Question 2), I mark whether it's a savings account, and only those appear in balances.

C) Other (please describe after [Answer]: tag below)

[Answer]: A. This is credit transactions are future spending, and credit bills are paid from real savings account later, if i also include credit-card accounts in balances, there will be confusion.

## Gap 3: Currency of balances
You asked for per-account balances plus a combined total (Q4 = B). Investigated: transactions already carry both an original `currency` and a `converted_amount_sgd`, and the app has an FX-rate cache, so a savings account in a foreign currency is possible. A combined total across accounts in different currencies can't be a plain sum.

### Clarification Question 4
How should currencies be handled?

A) Each account's balance is shown in that account's own currency; the combined total is converted to SGD using the FX rate for the requested date.

B) Every balance, per-account and combined, is shown in SGD only (converted using the FX rate for the requested date).

C) I only have SGD savings accounts, so currency conversion is not needed for this feature.

D) Other (please describe after [Answer]: tag below)

[Answer]: B

## Risk 1: Reingesting would discard your manual category corrections
You said you're willing to reingest everything. Investigated: `duplicate_detection/service.py` skips any PDF whose content hash already exists (`uq_bank_statements_pdf_content_hash`), so existing statements can't simply be run through ingestion again — they would have to be deleted first. Deleting them also deletes every transaction row, including the ones whose category you corrected by hand (`category_source`) and any recurring-payment matches tied to them.

### Clarification Question 5
How should the backfill be done?

A) Wipe all existing statements and transactions, then reingest every PDF from scratch. I accept losing my manual category corrections and any recurring-payment matches tied to existing transactions.

B) Wipe and reingest, but first capture my manual category corrections and re-apply them after reingest by matching on statement, date, amount, and description (best-effort; unmatched ones are reported to me).

C) Don't wipe anything: add a one-time backfill that re-reads each existing PDF only to populate the new account, account-type, and closing-balance data on its existing `BankStatement` row, leaving all existing transactions and corrections untouched.

D) Other (please describe after [Answer]: tag below)

[Answer]: B
