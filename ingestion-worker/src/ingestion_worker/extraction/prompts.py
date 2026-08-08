EXTRACTION_PROMPT = """You are reading a bank or credit card statement (page images attached). \
Extract the following as JSON matching exactly this shape, with no extra commentary:

{
  "bank_name": string or null,
  "currency": 3-letter ISO currency code or null (the statement's primary currency),
  "statement_date": "YYYY-MM-DD" or null (the date printed on the statement itself, \
often labelled "Statement Date" -- NOT a transaction date. Read it using the same \
day-first rule described below if the printed format is ambiguous),
  "confidence": "low" | "medium" | "high" (your overall confidence in this extraction),
  "transactions": [
    {
      "transaction_date": "YYYY-MM-DD",
      "description": string,
      "amount": positive number,
      "direction": "in" | "out" (in = money coming into the account, out = money leaving),
      "printed_converted_amount_sgd": number or null (ONLY if the statement itself prints \
an SGD-equivalent amount for this line, e.g. a foreign-currency transaction with the \
bank's own SGD conversion shown alongside it — do not compute this yourself, only report \
it if it is literally printed on the statement),
      "confidence": "low" | "medium" | "high"
    }
  ]
}

If you cannot confidently identify the bank name or currency, use null for those fields \
and lower your overall confidence accordingly. If a page appears to have no transactions \
(e.g., a cover page or summary-only page), it's fine for "transactions" to omit those \
rows — but if you cannot read the statement content at all, set confidence to "low" and \
return an empty transactions list rather than guessing.

Many statements (particularly Singapore-issued ones) print dates day-first, e.g. \
"31/01/26" or "31 Jan 26" meaning 31 January 2026 — NOT January 31st written as \
"01-31-26". Identify which printed numeral is the day and which is the month (using \
the statement's billing period/header as a sanity check if unsure), then write them \
into "YYYY-MM-DD" in the correct MONTH-then-DAY order. Do not simply copy the \
printed digit order into the month/day slots.

This is a bank or credit card statement: transactions are almost always listed in \
chronological (ascending date) order. Use that as a self-check — as you extract each \
row, the day values should generally stay the same or increase down the list (allowing \
for a reset at a new month). If you notice a value that breaks this pattern (e.g. it \
jumps backwards, or looks like a day value greater than 12 ended up in the month \
position), that is a strong signal you have day and month swapped for that row — \
re-examine the source digits and correct it before finalizing your answer.

Do NOT include any line that merely restates the account's running or outstanding \
balance as a transaction — for example "balance brought forward", "balance carried \
forward", "previous balance", "opening balance", "closing balance", "outstanding \
balance", "total outstanding balance", or an abbreviation like "bal b/f" / "bal c/f". \
None of these represent money that moved in or out on that date; they are a restated \
total, and including one would double-count against the real transactions that make \
up that balance. Omit any such line entirely from the "transactions" list, under \
whatever exact wording the statement uses for it.
"""
