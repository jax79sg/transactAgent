# Recurring Payments, Budget Alerts & Subscription Detection — Clarifying Questions

Your reference list of monthly/annual payments stayed in chat only — none of it is repeated here or written to any file (this repo is public). Options below use made-up examples (e.g. "Gym Membership") purely for illustration.

Please fill in each `[Answer]:` tag. Choose the last option (Other) and describe your preference if none fit.

## Question 1 — Reconciliation Against Actual Transactions
Should the app try to automatically match an incoming transaction (from ingestion) to an expected recurring payment, so it can mark that cycle "Paid" without you doing anything?

A) Yes — auto-match by category/description similarity + amount range + a due-date window (e.g. ±5 days), similar to how categorization already matches similar past transactions

B) No — purely a manual tracker; you mark each cycle "Paid" yourself once you see the transaction come through

C) Other (please describe after [Answer]: tag below)

[Answer]: C. Automatch as in A but make sure a human reviews and agrees before you do it automatically in future.


## Question 2 — Variable-Amount Payments
Some recurring payments genuinely vary each cycle (e.g. a utilities bill that's ~$275 some months, ~$310 others), unlike fixed ones (e.g. a loan installment that's always the same amount). How should these be handled?

A) Every recurring payment gets an "expected amount" used only as a rough guide — matching a transaction to it relies mainly on description/category + due-date window, with amount as a loose sanity check, not an exact match

B) You mark each recurring payment as either "Fixed" or "Variable" — Fixed ones require the matched transaction's amount to be close to expected (flagging a mismatch if not); Variable ones only track that *a* payment came in, not the amount

C) Other (please describe after [Answer]: tag below)

[Answer]: A


## Question 3 — Where This Lives in the App
Where should this feature live?

A) A new page in the main nav (e.g. "Bills"), alongside Dashboard/Transactions/etc.

B) Folded into the existing Dashboard page as a new section/tab

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 4 — Entering Your Recurring Payments
You have a real, existing list (~35 monthly + ~10 annual items) you'd want to start from. How should you get that into the app?

A) One-at-a-time add/edit form (like Settings' category management today) — you type each one in yourself after this feature ships

B) A bulk import (paste or upload a CSV of name/amount/frequency/due-date) so your existing list can be loaded in one step, in addition to the one-at-a-time form for later edits

C) Other (please describe after [Answer]: tag below)

[Answer]:B


## Question 5 — Annual Payment Lead Time
Annual bills tend to be large (insurance renewals, property tax, etc.). What kind of heads-up do you want for those?

A) A plain due-date reminder starting N days before (you pick N per item, or one global default)

B) The above, plus a "monthly set-aside" figure shown alongside it (expected annual amount ÷ 12) so you can see what you'd need to be saving each month to have it covered

C) Other (please describe after [Answer]: tag below)

[Answer]: B


## Question 6 — Overdue Definition
A recurring payment's due date passes with no matching transaction seen yet. When does it flip from "due soon" to "overdue"?

A) Immediately — the day after the due date with no match, it's overdue

B) A grace period first (e.g. 3 days) before flagging overdue, since due dates are often approximate

C) Other (please describe after [Answer]: tag below)

[Answer]: A


## Question 7 — Subscription Detection Scope
For automatically detecting recurring charges you haven't registered yet (the "subscription detection" half of this feature) — should detection attempt both monthly-cadence and annual-cadence patterns, or just monthly for this first version?

A) Monthly-cadence detection only for now (e.g. a similar description/amount appearing roughly every ~30 days, 2+ times in a row) — annual-cadence detection needs a lot more transaction history to be reliable, add it later

B) Attempt both monthly and annual-cadence detection from the start

C) Other (please describe after [Answer]: tag below)

[Answer]:A


## Question 8 — Linking to Categories
Should each recurring payment optionally link to one of your existing whitelist categories (so it can feed into the Dashboard's category views too), or stay entirely separate from categories?

A) Optional link to an existing category

B) Entirely separate — recurring payments are their own thing, no category link

C) Other (please describe after [Answer]: tag below)

[Answer]:A


## Question 9 — Alert Visibility
For this first version, how should "something needs your attention" (due soon / overdue / newly detected recurring charge) actually reach you?

A) In-app only — a nav badge (like the existing Review pending-count badge) plus a list on the Bills page, no email/external notification yet

B) In-app now, but also want email for at least the overdue/large-amount cases in this same version

C) Other (please describe after [Answer]: tag below)

[Answer]: A
