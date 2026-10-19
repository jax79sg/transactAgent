# Functional Design Plan — Ingestion Worker Service: Account Balance at a Point in Time (Epic 13)

Unit: Ingestion Worker Service. Scope: the extended **Statement Extraction** contract (account identifier, account type, closing balance), the new **Account Resolver Component**, the small change to the **Ingestion Orchestrator** and **Duplicate Detection**'s `recordProcessed`, a **delete/recreate operation on the Vector Store Client**, and the new **Backfill Tool Component** (US-13.1, 13.6, 13.7). Technology-agnostic: logical rules only; code is Code Generation.

Please answer the three questions at the bottom by filling in the letter after each `[Answer]:` tag. If none of the options fit, choose the last option (Other) and describe your preference. Let me know when you're done.

## What the live data says (read-only counts, taken 2026-10-03)

| | |
|---|---|
| Statements / transactions | **172** statements, **6,667** transactions, all in SGD |
| Manual category corrections | **794** transactions with `category_source = manual` |
| Rows that the backfill would discard | 1,978 recategorization proposals, 862 recategorization jobs, 35 categorization disagreements, 4 recurring-payment matches |
| Raw bank names | 15 distinct values over 172 statements: `CIMB BANK` / `CIMB Bank`, `DBS` / `DBS / POSB` / `POSB`, `GXS Bank` / `MariBank`, `HSBC`, `Maybank`, `OCBC` / `OCBC Bank`, `Trust` / `Trust Bank` / `Trust Bank Singapore Limited`, `UOB` |

## Design decisions made and explained (not asked), with reasoning

| Topic | Decision | Why this isn't a question |
|---|---|---|
| **Extraction contract** | Statement extraction gains four optional fields: `account_identifier` (the account number exactly as printed, null if none), `account_type` (`deposit` / `credit_card` / `unknown`), `closing_balance`, and `closing_balance_date`. None of them can fail an extraction: a statement missing any still ingests (A-2, A-3, NFR-AB-3); WR-1/WR-2 and the confidence gate are unchanged. The prompt asks for a closing balance **only for savings/current statements** and null for credit cards, whose printed "outstanding balance" has the opposite meaning and is never used. Overdrawn or debit balances are read as negative. | Direct translation of FR-AB-2/4/5. Limiting the balance to deposit statements refines the Database design's "stored as printed" note: nothing reads a credit statement's balance, and a null avoids storing a number whose sign means something different. |
| **Closing-balance date is date-checked like every other date** | `closing_balance_date` goes through the same defenses as transaction dates: it is corrected by the existing whole-document day/month swap when that fires, and otherwise cross-validated the way `statement_date` already is (it must fall on or shortly after the latest unambiguous transaction date). A date that fails validation falls back to the validated `statement_date`; if neither is trustworthy, **both** closing fields are dropped (BR-33) and the statement simply has no cross-check. | The model has been observed misreading day-first dates in this exact codebase (the OCBC incidents recorded in `extraction/service.py`); a wrong closing date would raise false discrepancy warnings (US-13.6), so it gets the same protection. |
| **Bank-key normalization** (computed by the application, stored in `AccountKey.bank_key`) | Case-fold; replace punctuation with spaces; remove the generic whole-word tokens `bank`, `limited`, `ltd`, `pte`, `singapore`, `sg`; collapse spaces; if nothing is left, keep the case-folded original. Checked against the live data: the 15 raw names become 11 keys (`cimb`, `dbs`, `dbs posb`, `posb`, `gxs`, `maribank`, `hsbc`, `maybank`, `ocbc`, `trust`, `uob`; `OCBC`/`OCBC Bank`, the three `Trust` variants, and `CIMB BANK`/`CIMB Bank` each collapse to one). `DBS`, `DBS / POSB`, `POSB`, and `GXS Bank` vs `MariBank` deliberately **stay separate**. | `DBS` and `POSB` are different brands a person may hold separately, and `GXS Bank`/`MariBank` is a rename no rule can know. The Database design's merge (BR-35) exists precisely so you resolve those yourself, once, and it sticks. |
| **Account identifier normalization** | Remove whitespace and hyphens only (Question 1 of the Database design = as printed); keep every other character, including mask characters, as printed. | Settled by your earlier answer. |
| **Default account name** | `<display bank name> <last 4 characters of the identifier>`, or just the display bank name when the statement prints no identifier. The display bank name is the raw name from the first statement, trimmed. | Shows only a short tail on screen even though the full number is stored; the user can rename it (US-13.2). |
| **Type rules** | Set from extraction when the account is created. While the user has not corrected it (`type_user_set` false): `unknown` may be upgraded to `deposit` or `credit_card` by a later statement; if two *known* types disagree, the **existing type is kept** and a warning is written to the ingestion run log, so a single misread month can never flip an account in or out of balances. Once the user has set it, extraction never changes it (BR-34). | Extends BR-34 with the one case it left to this stage. Keeping the first known type is the safe default because a wrong flip silently adds or removes an account from your balances. |
| **Where resolution runs** | In the per-file flow after extraction succeeds and before the statement is recorded, in the **same database transaction** as the statement and its transactions, so a file that fails after resolution leaves no orphan account. Each resolution writes a line to the run log ("linked to existing account" / "created account") for the Ingestion page. | Matches how a file's other writes already behave, and the Application Design already placed the step there. |
| **Vector-store cleanup (the Database design's flagged gap)** | The Vector Store Client gains one operation: **recreate the `transactions` collection empty** (the backfill wipes *every* transaction, so every point in that collection is orphaned). The recurring-payment-name collection is untouched. It runs **after** the database wipe has committed; the tool refuses to start the reingest until it succeeds. | Deleting points one by one would be slower and need the old ids; since the whole collection is stale, recreating it is simpler and cannot leave a straggler. Doing it after the commit means a failure leaves harmless ghost vectors (the tool reports it and retries) rather than a wiped vector store beside intact data. |
| **Backfill: protects statements it cannot re-create** | The dry run checks that every existing statement's source PDF (`drive_file_id`) is still in the Drive folder. A statement whose PDF is **missing from Drive is never wiped**: it is left exactly as it is (with its dependent rows) and listed in the report. | Wiping a statement whose PDF no longer exists would destroy data that can never be re-created, which no part of the approved scope intended. This refines FR-AB-15 from "wipe all" to "wipe all that can be re-ingested". |
| **Backfill: no concurrent ingestion** | The tool refuses to start while any ingestion run or recategorization job is queued or running. Its own reingest then holds the single active-run slot (BR-10's partial unique index), so no normal run can be queued or started while it works. The runbook also says to stop the `ingestion-worker` service first so its background work (embedding batches, backups) cannot interleave; the tool restarts nothing itself. | BR-10 already gives mutual exclusion for free; no change to the worker's poll loop is needed. |
| **Backfill: the wipe is one transaction** | The database wipe (Database design BR-36 order) happens in a single transaction: all of it or none of it. | Never leaves a half-wiped database. |
| **Backfill: a typed confirmation** | The tool prints the exact counts that will be wiped, then requires typing a confirmation that includes the statement count (for example `WIPE 164 STATEMENTS`). Anything else aborts with nothing changed. | A phrase that includes the real number cannot be typed by habit. |
| **Backfill: two phases, resumable** | `run` does the dry run, backup, confirmation, wipe, vector cleanup, and reingest. `finish` re-applies the preserved data and writes the completion report; it reads what to re-apply from the **backup artifact**, not from memory. If the reingest is interrupted, the existing "run ingestion" button in the app completes it safely (content-hash duplicate detection skips what already succeeded), and `finish` runs afterward. | A crash between the wipe and the end of the reingest must never lose the corrections, which would be the case if they lived only in the tool's memory. |
| **Backfill: correction matching** | Match by (statement content hash, transaction date, amount, direction, description) as a **multiset**: if several reingested transactions share a key, apply as many captured entries as there are rows, in statement order; any left over is reported as unmatched. Re-applied categories are written **directly**, never through the normal correction path, so they do **not** create recategorization jobs (which would trigger a re-scan storm). | Identical rows are interchangeable from your point of view, so "which of two identical rows" cannot matter. |
| **Backfill: report** | Printed and also saved next to the backup in Drive: counts wiped and re-ingested, statements kept because their PDF is missing, PDFs that failed to reingest with reasons, unmatched corrections individually, recurring-payment matches re-derived, dependent row kinds discarded. | FR-AB-17 / US-13.7. |
| **Expected effort (for your awareness)** | The reingest re-reads **172 PDFs** through the Gemini extraction call and re-runs the categorization step for **6,667 transactions** — the same work as the original ingestion. It will take a long time and use API quota proportional to that. | Not a design choice; stated so it is not a surprise. |

## Open questions

### Question 1
Some banks send one PDF covering several accounts (for example a consolidated statement with a savings and a current account). The whole design, like the existing extraction, assumes **one PDF = one bank, one currency, one account** (A-6). Does that hold for the statements you load?

A) Yes: every PDF I load holds exactly one account. No special handling.

B) Some PDFs hold several accounts. Detect and **flag** them: they are still ingested as one account exactly as today, extraction notes that more than one account was seen, and the completion report lists those statements so I know which accounts' balances to distrust.

C) Some PDFs hold several accounts and I want them handled properly (each account's section becomes its own statement and account). This is a materially larger change to extraction and ingestion than anything above, and would be worth planning separately rather than inside this feature.

D) Other (please describe after [Answer]: tag below)

[Answer]: C

### Question 2
The backfill must take a **verified backup** before wiping anything (NFR-AB-2), and — as above — its `finish` step reads your preserved data from that backup. The worker's container image has no `pg_dump`, and nothing in the stack writes to your disk. Which backup should it be?

A) A **Python export** of every table the wipe touches (statements, transactions, and the four dependent tables) as one file per table plus a manifest of row counts and checksums, uploaded to your existing Drive backup folder in a timestamped subfolder, then **downloaded back and re-counted** to verify. The tool also gets a `restore` command that reloads from it. No image or compose change. Tradeoff: the restore command is new code that must be tested, and the files are not readable by standard database tools.

B) A real **`pg_dump`**, restorable with standard tools. The worker image would need a newer PostgreSQL client than its base image carries by default (the default is older than your PostgreSQL 16 server, and refuses to dump it), so this means a Dockerfile change. The `finish` step would also still need a small side file with the preserved categories, since it is awkward to read them back out of a dump.

C) The same Python export as A, written to a **new folder on your computer** (a new bind mount in the compose file) instead of Drive. Tradeoff: needs a docker-compose change, and the backup lives only on this machine.

D) Other (please describe after [Answer]: tag below)

[Answer]:A

### Question 3
The approved scope preserves your **794 manual corrections** only. Everything else — the other **5,873** transactions, whose categories came from similarity matching or the language model — would be **recategorized from scratch** during the reingest, and the result will not necessarily match today's categories (the similarity matcher learns from past transactions, and at the start of the reingest there are none). You asked for exactly this kind of change not to happen as a side effect once before (the embedding rework: "their current assigned categories should not change"). What should happen to those 5,873?

A) Let the pipeline recategorize them freshly, as approved. Only manual corrections are preserved. Cheapest to build, but a large share of categories may change.

B) Also **preserve every transaction's current category and category source** using the same matching as the manual corrections, so categories do not change for anything the matching can identify. The pipeline's own categorization still runs during the reingest (same cost as A) and is then overwritten for matched rows; anything unmatched keeps the fresh result and is reported. Tradeoff: slightly more to build and report, and the matched rows' original sources (`similarity`, `llm`) are kept as they were.

C) Other (please describe after [Answer]: tag below)

[Answer]:A

## Steps

- [x] `domain-entities.md`: add the extended extraction DTO fields and the Account Resolver's input/output, with a note on the closing-balance validation fallback.
- [x] `business-rules.md`: add **WR-44..** covering: extraction fields optional and never failing extraction; closing-balance only for deposit statements and its date validation chain; bank-key and identifier normalization; default account name; type rules (upgrade-only, keep on disagreement); resolution in the file transaction; vector-collection recreation; backfill pre-flight (no active run, missing-PDF protection); single-transaction wipe; typed confirmation; two-phase resumable flow; correction matching (multiset, direct writes); report; plus the outcome of Questions 1 to 3.
- [x] `business-logic-model.md`: add sections for the Extraction addendum, the Account Resolver Component, the Ingestion Orchestrator / Duplicate Detection addenda, the Vector Store Client's recreate operation, and the Backfill Tool Component's `run` and `finish` flows.
- [x] Dated notes in `components.md`, `component-methods.md`, and `account-balance-requirements.md` for anything refined here (FR-AB-15's "wipe all" becoming "wipe all that can be re-ingested"; Question 3's outcome if it widens FR-AB-16).
- [x] Validate against FR-AB-2, 4, 5, 15, 16, 17, A-2, A-3, NFR-AB-2, NFR-AB-3 and US-13.1, 13.6, 13.7: every behavior lands on a rule or section.
- [x] Update `aidlc-state.md`

## Mandatory Artifacts
- [x] `domain-entities.md`: updated in place
- [x] `business-rules.md`: updated in place (WR-44..)
- [x] `business-logic-model.md`: updated in place

## Outcome of the questions and amendments to this plan (2026-10-03)

- **Question 1 = C, clarified to B**: several accounts per PDF are handled **in this feature** (see `ingestion-worker-account-balance-functional-design-clarification-questions.md`). This replaced the plan's one-account-per-PDF assumption and reopened the Database design and code; the extraction decision above now reads "returns account sections" (WR-44..WR-47).
- **Question 2 = A**: Python export to a timestamped Drive subfolder, verified by read-back, with a `restore` command (WR-54).
- **Question 3 = A**: only manual corrections are preserved; the pipeline's fresh categorization stands for everything else (WR-55).
- **Refinement of the backfill's wipe set** (found while designing resumability): a statement is wiped only if it has **no account sections yet** and its PDF is **still in Drive**. This makes re-running safe and an interrupted run resumable, and it supersedes the plan's earlier "every statement whose PDF is present" wording (WR-53).
