# Issues #65 to #70: review, priority and plan

2026-11-15. All six issues were filed the same morning by the owner. Each is one or two sentences, so the first job was to find out what is true. The checks below were read-only queries on the live database (names, types and counts only, never amounts) plus the worker's log.

## What the data says

The six reports are two root causes and two real data situations, not six separate bugs.

**Root cause A: the Transactions page knows banks, the Balances tab knows accounts.** The Transactions page lists the distinct `bank_name` text on each transaction: 13 strings, with the same bank spelled several ways ("OCBC" and "OCBC Bank", "Trust", "Trust Bank" and "Trust Bank Singapore Limited", "DBS" and "DBS / POSB"). The Balances tab lists the 20 accounts. A transaction does carry its account (`statement_account_id`), but no screen shows it and no filter uses it. So nothing on the Transactions page can ever match "DBS 6220", "MariBank 8101" or "GXS Bank cket". (#65, #66, #67, #69.)

**Root cause B: a name tells you nothing about the kind of account.** Accounts are named `<bank> <last 4 of the number>`; nothing says savings or credit card. "OCBC Bank 5001" is a current account and "OCBC Bank 4002" a credit card. (#68.)

| Issue | What is actually going on | Data lost? |
|---|---|---|
| #65 DBS 6220 and DBS / POSB 6220 | One real account (the same account number) under two bank spellings. The approved design keeps `DBS`, `DBS / POSB` and `POSB` as separate bank keys on purpose, "the user resolves those once with a merge". Nothing tells the owner they are the same, **both have a balance entered, so the combined total counts the account twice.** | No. Money is overstated. |
| #66 two "GXS Bank cket" | Two different GXS Boost Pockets. The account number the statement prints is a name (`...BoostPocket`), and the default name takes the last 4 characters, "cket", for both. Each pocket has its own statement and its own (interest) transactions: nothing is counted twice. | No. Names are useless. |
| #67 desync | Root cause A. | No. |
| #68 deposit versus credit | Root cause B. | No. |
| #69 MariBank 8101 | A real, idle account: it appears on several statements alongside another account but has no transactions on any of them. Nothing was lost; it simply cannot appear in a transaction list. | No. |
| #70 MLife savings ending 7403 | No statement the app has ever read mentions 7403 or MLife. The last ingestion run was 2026-10-05. **Google Drive's refresh token is no longer valid** (`invalid_grant`): the nightly backup has failed every night since at least 12 Oct, a download would fail the same way, and Settings still says "Connected". The likeliest reading is that the statement was added to Drive after the last run and cannot be fetched. | Not lost: never fetched. |

Other findings, not part of the six: one July 2026 GXS statement ingested on 2026-09-03 has 99 transactions and no account (the backfill never attributed it), so those 99 sit in no account's balance; the Balances tab already flags such transactions in its "not in any account" notice, and on the Transactions page they now show "—" in the Account column. 17 statements fail with "Zero transactions extracted" on every run; the ones inspected are accounts with no activity that month (a CIMB card 7597, an HSBC card 3071, several DBS/POSB months with a closing balance and no transactions).

## Priority

1. **#65** (a number on screen is wrong; the owner is relying on the total).
2. **#70** (backups and ingestion are silently dead, and the screen says they are fine).
3. **#67 and #69** (the root cause behind four of the six reports).
4. **#66** (a name bug, once the account column makes names visible it matters more).
5. **#68** (labelling).

## Resolution

| Issue | Change | Needs the owner afterwards? |
|---|---|---|
| #65 | Balances tab warns when accounts share an account number and offers the existing Merge dialog for the pair. The conservative matching design is unchanged. | **Yes: one merge click on live data** (a merge is the owner's decision). |
| #66 | New accounts with a non-numeric identifier are named from the whole identifier, split into words ("GXS Bank Alpha Boost Pocket"). A narrow data migration renames the existing accounts that carry the old broken pattern, and only those. | No. |
| #67 | Transactions gets an **Account** filter (every account, including ones with no transactions, each with its type and count) and an **Account** column; the API filters by `accountId` and returns each transaction's account. | No. |
| #68 | Account type is shown wherever an account is named: the Balances table, the Transactions filter and column. | No. |
| #69 | Follows from #67: MariBank 8101 appears in the Account filter, marked "0 transactions", so the apparent contradiction is gone. | No. |
| #70 | Settings tells the truth: when Google refuses the saved sign-in, the Drive card says so and what stops working. The reconnect itself is Google's consent screen and cannot be done for the owner. | **Yes: reconnect Drive, then run an ingestion.** |

Not changed, deliberately: how accounts are matched (the design says merge, not guess); how many balances an account has; the 99 unattributed GXS transactions and the zero-activity statements (separate pieces of work, reported to the owner).

## Steps

Test first for each; tick as done.

- [x] 1. API: `accountId` filter and per-transaction `account` on `GET /transactions` (and the filter on the CSV export and group totals).
- [x] 2. API: `GET /drive/status` reports `needsReconnect` when Google refuses the saved credential.
- [x] 3. Worker: default account name for a non-numeric identifier.
- [x] 4. Database: data migration renaming existing accounts with the old pattern; test it.
- [x] 5. Frontend: Transactions Account filter and column, with the account type.
- [x] 6. Frontend: account type shown on the Balances table.
- [x] 7. Frontend: possible-duplicate notice on the Balances tab, opening the Merge dialog.
- [x] 8. Frontend: Settings Drive card for an expired connection.
- [x] 9. e2e: Transactions by account.
- [x] 10. Amend the approved design documents and the code summaries in place.
- [x] 11. Run every suite and lint; confirm the new tests fail without the change.
- [ ] 12. Dispatch the e2e workflow on the branch and read it.
- [ ] 13. PR, bind, auto-fix; a comment on every issue (what was found, done, and left for the owner); update audit and state. Not merged, not released, not deployed.
