# Ingestion Worker — Account Balance: Functional Design Clarification Questions

Thanks. Two of your three answers are settled and need no follow-up:

- **Question 2 = A**: the backfill's backup is a Python export of every table the wipe touches, uploaded to your Drive backup folder in a timestamped subfolder, read back and re-counted to verify, with a `restore` command in the same tool. No image or compose change.
- **Question 3 = A**: only your 794 manual corrections are preserved; the other 5,873 transactions are recategorized freshly by the pipeline during the reingest, and their categories may differ from today's.

One answer needs a follow-up before I can continue.

## Ambiguity 1: Question 1 = C (multi-account PDFs "handled properly")

You chose option C: *some PDFs hold several accounts, and you want them handled properly (each account's section becomes its own statement and account)*. That option, as I wrote it, carried a warning: it is a **materially larger change** than everything planned so far, "worth planning separately rather than inside this feature". Your answer does not say whether you want it inside this feature despite that, or as a separate follow-up, and the two lead to very different work, so I don't want to guess.

**What I can and cannot tell from your data.** Nothing stored today records how many accounts a PDF held: extraction keeps one bank name and one currency per statement and discards the rest, so I cannot see from the database which of your 172 statements are multi-account.

**What "handled properly" would mean concretely, so you can weigh it:**
- Today's design (approved, and already built in the Database unit) gives each PDF exactly one account and one closing balance, stored on the statement itself. Several accounts in one PDF needs a different shape: a per-statement-per-account record holding that account's closing balance, and transactions tied directly to an account rather than inferred from their statement.
- That would **reopen the approved Database design and its generated code** (the new columns on the statement, migration 0019, the tests), reopen the Application Design and Epic 13's stories (US-13.1's "one statement belongs to one account"), and change assumption A-6.
- The extraction itself would change from "one list of transactions" to "a list of accounts, each with its own transactions". The existing safeguards rely on one chronological list per statement (the day/month correction in particular), so they would need reworking per section, which is exactly the area your extraction has had real date-misread incidents in.

### Clarification Question 1
Which way do you want to go?

A) **Defer.** Finish this feature on the one-account-per-PDF design, but **detect and flag** multi-account PDFs: extraction records when it saw more than one account, those statements are still ingested as one account exactly as today, and the backfill's completion report lists them so you know whose balances to distrust. Proper multi-account handling then becomes its own separate, planned feature, informed by real flagged examples rather than guesses.

B) **Include it now.** Rework the approved Database design and code, the Application Design and stories, and the extraction, so each account section of a PDF becomes its own account and closing balance, and then carry on with the rest of this feature on top of that.

C) Other (please describe after [Answer]: tag below)

[Answer]:B

### Clarification Question 2
Whichever you choose, it helps to know how widespread this is. Which of your banks send PDFs holding more than one account? (Your banks, from the live data: CIMB, DBS / POSB, GXS Bank / MariBank, HSBC, Maybank, OCBC, Trust, UOB.)

A) None that I'm aware of — I picked option C earlier in case any do.

B) One or two of them (name them under Other below).

C) Most of them.

D) Not sure — I'd rather find out from the detection in option A above.

E) Other (please describe after [Answer]: tag below)

[Answer]:D
