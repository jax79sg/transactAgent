# Probable Duplicate Statement Detection — Requirements

## Intent Analysis Summary

- **User Request**: "Let's tackle this as a new feature 'Not recognized: the same statement as a different file.'" — arising from the question "If there are duplicate pdf statements, will the code be able to recognise?"
- **Request Type**: New Feature (closes a data-integrity gap)
- **Scope Estimate**: Multiple Components, all four units:
  - **Database**: a new ingestion-file outcome for a skipped probable duplicate; a remembered record of flagged and removed files; the stored comparison snapshot; a removal job.
  - **Ingestion Worker Service**: detection after extraction, the remembered-hash check before extraction, the removal job (including the transactions' embeddings), and integration with the Backfill Tool.
  - **API Service**: endpoints for the duplicate list, the comparison view, confirm-remove, dismiss, and override.
  - **Frontend SPA**: a panel and badge on the Review page, and the "probable duplicate of <statement>" link and comparison view in the Ingestion run results.
- **Complexity Estimate**: Complex — two data-loss risks pull against each other (wrongly skipping a legitimate statement; wrongly deleting the copy that carries manual corrections), the check must be accurate on small statements, and it must work inside the Account Balance backfill.
- **Requirements Depth**: Comprehensive.
- **Extension Configuration (carried over unchanged)**: Security Baseline = No, Resiliency Baseline = No, Property-Based Testing = Partial. The match-ratio calculation and the comparison-snapshot selection are pure functions and fall within the Partial PBT scope.

## Findings That Shaped These Requirements

Established by inspecting the code and the live data (read-only; names, dates, and counts only) on 2026-10-03:

1. **Today's duplicate prevention hashes the PDF's raw bytes and nothing else** (`duplicate_detection/service.py`). Byte-identical files are caught: 3 of the user's Drive files were exact copies and were skipped; all 172 statements have distinct hashes. There is no transaction-level or period-overlap check anywhere in the worker.
2. **Two confirmed duplicate pairs exist, both June 2026.**
   - *UOB*: files `JUN 2026_20260728074739457.pdf` and `JUN 2026_20260828174121571.pdf` (names embed a download timestamp a month apart); 5 and 5 transactions, all 5 identical; 2 manual corrections on the first copy.
   - *Trust Bank*: 8 and 8 transactions, all 8 identical; 2 manual corrections on the *other* copy. The two statements carry different spellings of the bank name, so detection must use the normalized bank key from the Account Balance work.
3. **Two CIMB pairs each share exactly one transaction between one-transaction statements**, indistinguishable from coincidence on transactions alone (for example two accounts receiving the same interest).
4. **A skipped probable duplicate is never recorded as a statement**, unlike an exact duplicate (which is recognized by hash *before* extraction). Left alone, every later ingestion run would download and re-read it with Gemini again. It therefore has to be remembered by its content hash.
5. **The API Service never connects to the vector store** (the project's one hard rule is that the two services coordinate only through the database), and the vector store client has no per-point delete operation today. Removing an ingested statement therefore has to be carried out by the Ingestion Worker.
6. **The Account Balance backfill re-reads every PDF.** Unless this feature is in place first, it would recreate both duplicate pairs, and its correction matching (keyed by a statement's content hash) would lose the manual corrections that sat on whichever copy a duplicate check skipped.

## Functional Requirements

### Detection at ingestion

- **FR-PD-1**: After a file is successfully extracted and **before** any account, statement, section, or transaction is created, the system shall compare it against the already-ingested statements. If it is a probable duplicate (FR-PD-3), it is **skipped automatically**: nothing is ingested and no account is created from it.
- **FR-PD-2**: A skipped probable duplicate shall be recorded against its ingestion run file with a distinct outcome (separate from the existing exact-duplicate outcome) that names the statement it matches and states the reason (how many transactions matched, same bank, overlapping period). In the run results it appears as **"probable duplicate of <statement>"**.
- **FR-PD-3**: A file is a **probable duplicate** of an existing statement when all of these hold: the same normalized bank; the same account **when both sides have an account identifier** (A-PD-1); overlapping periods; and **at least about 80%** of the transactions of the smaller of the two statements match transactions of the other on date, amount, direction, and description, tolerating the small wording differences that can appear when the same PDF is read twice (A-PD-2).
- **FR-PD-4**: A statement with **fewer than 3 transactions** (either side) shall **never** be treated as a duplicate on transactions alone. For such statements the account identifier **and** the closing balance and its date must also match, which are available only after the Account Balance backfill; until then, such statements are never flagged.

### Evidence and override

- **FR-PD-5**: When a probable duplicate is skipped, the system shall store a **comparison snapshot** with the skip record, because the skipped file's transactions exist nowhere else: up to **10 transactions from each side, the 10 largest by amount (ties: earlier date first)**, each marked **"also on the other statement"** or **"only on this one"**, together with the headline figures (transaction counts, periods, matched count). The "original" side is captured at detection time.
- **FR-PD-6**: Clicking "probable duplicate of <statement>" in the run results shall open a comparison view showing the two snapshots side by side, so that a person can be sure.
- **FR-PD-7**: From the comparison view the user can declare **"Not a duplicate — ingest it"**. The file is then ingested on the next ingestion run, and the decision is remembered so the same file is never flagged again (A-PD-4).
- **FR-PD-8**: Every skipped probable duplicate is **remembered by its content hash**, so later runs recognize it before extraction, as they do for exact duplicates, and do not download and re-read it again.

### Existing duplicates

- **FR-PD-9**: Duplicates already ingested (such as the two June pairs) shall be found by applying the same rule (FR-PD-3, FR-PD-4) to the stored statements, and listed in a **"Probable duplicate statements" panel on the Review page** with a count badge in the navigation, following the existing review flows. Each pair shows the same comparison as FR-PD-6, the copy proposed to be kept (FR-PD-11), and how many manual corrections each copy carries.
- **FR-PD-10**: Nothing is removed without the user's explicit confirmation in the app. Confirming removes the proposed duplicate (FR-PD-12). The user can instead **dismiss** a pair as "not a duplicate"; the dismissal is remembered so the pair is not flagged again (A-PD-5).
- **FR-PD-11**: **Which copy is kept**: the copy carrying manual category corrections; if neither or both carry some, the **earlier-ingested** copy. When both carry corrections, the corrections on the removed copy are lost, and the confirmation shall state that count before the user confirms. There is no "swap" control; a user who disagrees with the proposal dismisses the pair (A-PD-6).

### Removal

- **FR-PD-12**: A confirmed removal **permanently deletes** the duplicate statement and its transactions, and everything that depends on them (recategorization jobs and proposals, categorization disagreements, recurring-payment matches, and its account-section rows once the Account Balance feature is in place), **and the removed transactions' embeddings from the vector store**. The file in Drive is left alone. The confirmation shall state exactly what will be deleted (counts).
- **FR-PD-13**: A removed copy shall be remembered by its content hash as a **confirmed duplicate**, so the Drive file that remains is never re-ingested.
- **FR-PD-14**: Removal is all-or-nothing and is carried out by the Ingestion Worker (NFR-PD-4); the app shows it as pending, then done or failed.

### Backfill integration

- **FR-PD-15**: The Account Balance Backfill Tool's re-read shall apply the same detection. Its **dry run shall list the probable-duplicate pairs among the existing statements that it will skip**, and which copy it will keep (FR-PD-11).
- **FR-PD-16**: During the backfill's reingest the **copy FR-PD-11 would keep is the one retained**, and the other is skipped as a probable duplicate with its comparison snapshot recorded.
- **FR-PD-17**: **Manual corrections that sat on the skipped copy shall be carried to the matching transactions of the kept copy** instead of being reported as unmatched, since the backfill's correction matching is keyed by a statement's content hash and the skipped copy no longer has a statement. The completion report lists the skipped duplicates and the corrections carried.
- **FR-PD-18**: This feature shall be built and in place **before** the Account Balance backfill is run (Q7 = A), so that the backfill resolves the two existing pairs.

## Non-Functional Requirements

- **NFR-PD-1 (Accuracy, demonstrated on real data)**: Before the feature is enabled, the rule shall be evaluated read-only against the live statements. Acceptance: both June pairs (UOB, Trust) are flagged; the two CIMB one-transaction look-alikes are **not**; and **no other pair among the existing statements is flagged** without the user's explicit review of it.
- **NFR-PD-2 (No repeated cost)**: A flagged or removed file is never re-read by Gemini on later runs (FR-PD-8, FR-PD-13).
- **NFR-PD-3 (Safe deletion)**: Nothing is deleted without confirmation in the app; the confirmation states the counts and any manual corrections that will be lost; removal is all-or-nothing. Because a duplicate's transactions are by definition also on the kept copy, the only irreversible loss is manual corrections on the removed copy, which the confirmation names.
- **NFR-PD-4 (Architecture)**: The API Service never connects to the vector store. Removal is requested through the database and executed by the Ingestion Worker, consistent with the project's rule that the two services coordinate only through shared rows.
- **NFR-PD-5 (No silent loss in the backfill)**: Every file the backfill skips as a probable duplicate is reported with its comparison snapshot, and can be overridden afterward (FR-PD-7); a false positive can therefore be recovered from.
- **NFR-PD-6 (No regression)**: Exact-bytes duplicates are still skipped before extraction, exactly as today. Statements that are not duplicates ingest exactly as before, and the existing review flows, badges, and Ingestion page behave as before.
- **NFR-PD-7 (Testing)**: The match-ratio calculation and the snapshot selection are pure functions with property-based tests (symmetry of the match, ratio bounds, selection returns at most 10 and is the largest). Detection, removal, override, and backfill integration have conventional tests, including the two real-data shapes (identical sets with different bank-name spellings; manual corrections on only one copy).
- **NFR-PD-8 (UI consistency)**: New UI respects the existing light/dark theme and responsive behavior, and the new endpoints require the same authentication as the existing API.

## Documented Assumptions

Not explicitly decided by the user; included for review at approval:

- **A-PD-1 (Account matching)**: "Same account" is required only when **both** statements have an account identifier (after the Account Balance backfill). Before it, detection uses bank plus transactions, which is why small statements are excluded by FR-PD-4.
- **A-PD-2 (How the 80% is measured)**: against the smaller statement's transactions, with the exact tolerance for wording, the definition of "overlapping periods", and the threshold values calibrated in Functional Design against the live data (NFR-PD-1). The threshold and the small-statement minimum are expected to be settings on the existing Settings page.
- **A-PD-3 (The statement label)**: "<statement>" in "probable duplicate of <statement>" is its file name, bank, and period (for example `JUN 2026_2026… (UOB, 2 Jun to 30 Jun 2026)`).
- **A-PD-4 (Override timing)**: "Not a duplicate — ingest it" takes effect on the **next** ingestion run, not instantly.
- **A-PD-5 (Dismissal)**: dismissing an existing pair is remembered by the pair, so it is not flagged again.
- **A-PD-6 (No swap)**: the proposed keep/remove choice follows the Q6 rule and cannot be swapped in the panel; the user's alternative is to dismiss the pair.
- **A-PD-7 (Two new duplicates in one run)**: if two files in the same run are duplicates of each other, the first processed is kept and the second is skipped as a probable duplicate of it.
- **A-PD-8 (Remembered records)**: flagged, overridden, dismissed, and removed decisions are remembered by content hash (and by pair for dismissals), in the database.

## Open Items Deferred to Design

- The matching tolerance algorithm and the period-overlap definition (calibrated per NFR-PD-1).
- Where the comparison snapshot and remembered records live (new table versus new columns), and the enum change for the new ingestion-file outcome.
- The removal job mechanism and its status reporting (FR-PD-14).
- How the backfill orders copies so the FR-PD-11 copy is retained, and how it carries corrections across (FR-PD-16, FR-PD-17).
- Whether detection also needs a read-only preview command like `check-extraction` (FR-PD-15 asks only for the dry-run listing).

## Answers to Clarifying Questions (source of truth)

### Round 1: `probable-duplicate-statements-questions.md`

| # | Question (short) | Answer |
|---|---|---|
| 1 | Handling at ingestion | A: skip automatically and record as "probable duplicate of <statement>" with the reason, visible and overridable; **plus** keep a record of the top 10 transactions of both sides so a person can click through and be sure |
| 2 | How alike | B: same bank and period, at least about 80% of transactions match, tolerating wording differences |
| 3 | Very small statements | A: fewer than 3 transactions never flagged on transactions alone; also require account identifier and closing balance to match |
| 4 | Existing duplicates | A: a list in the app (Review-page panel with badge) where the user confirms which copy to remove |
| 5 | What "remove" means | A: delete the duplicate statement and its transactions permanently (the Drive file is left alone) |
| 6 | Which copy is kept | A: the copy carrying manual corrections; if neither or both, the earlier-ingested one |
| 7 | Sequencing with the Account Balance backfill | A: build this first, so the backfill's re-read applies the detection and resolves the two existing pairs |

### Round 2: `probable-duplicate-statements-clarification-questions.md`

| # | Question (short) | Answer |
|---|---|---|
| 1 | Which 10 transactions | A: the 10 largest by amount on each side (ties: earlier date first), each row marked "also on the other statement" or "only on this one" |

## Amendments

- **2026-10-04 (Ingestion Worker Functional Design, Question 1 = C)** — *a statement of clearly different size.* FR-PD-3 measures a match against the **smaller** statement, so a new file that wholly contains a smaller held statement plus more transactions of its own matches 100%. It is still flagged and skipped at ingestion (FR-PD-1, FR-PD-2), but the reason and the comparison state the size difference prominently (both counts, which is larger, and how many transactions on the larger side have no match), and the user can override (FR-PD-7). For statements already held (FR-PD-9, FR-PD-10, FR-PD-12), a pair whose sizes differ clearly — the smaller side has fewer than `duplicate_match_ratio` times the larger side's transactions — is **listed for information only**: the user can dismiss it but **no remove action is offered**, so removal is possible only when the two are the same size. For pairs where removal is offered, the confirmation also states how many transactions exist only on the copy being removed. The Backfill Tool's reingest never skips a different-size match (FR-PD-16), so such a pair stays for the panel. No new setting: the existing match ratio is used in both directions. (Live data check, 2026-10-04: none of the 172 statements is in this situation.)

## Summary

Add detection of the same statement arriving as a different file. After extraction and before anything is created, a file is compared with the statements already held; if the same bank (and account, when known), an overlapping period, and about 80% of the smaller statement's transactions match, it is skipped automatically and recorded as "probable duplicate of <statement>" with a stored comparison of the 10 largest transactions on each side, viewable by clicking through, with an "ingest it anyway" override. Very small statements are never flagged on transactions alone. Duplicates already ingested (the UOB and Trust June pairs) are listed in a Review-page panel where the user confirms removal, which permanently deletes the duplicate, its transactions, and their embeddings, keeping the copy that carries manual corrections (else the earlier). Flagged and removed files are remembered by content hash so they are never re-read. The feature is built before the Account Balance backfill, whose dry run lists the pairs it will skip and whose reingest keeps the right copy and carries manual corrections across.
