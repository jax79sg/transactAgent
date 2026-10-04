# User Stories — Probable Duplicate Statement Detection

Appends **Epic 14** to the project's existing story set (`stories.md` Epics 1–5, then Epics 6–13 in their own files, the latest being `account-balance-stories.md` Epic 13), kept separate so prior history stays untouched.

**Persona**: **The Account Owner** (`personas.md`), unchanged. This feature introduces no new persona.
**Granularity/format**: Coarse, epic-level, Given/When/Then plus edge cases, matching the existing convention.
**Traceability**: Each story references `probable-duplicate-statements-requirements.md`'s FR-PD, NFR-PD, and A-PD (documented assumption) IDs. Where an acceptance criterion rests on a documented assumption, it says so, so approving these stories also confirms those assumptions.

**Real cases used throughout** (from the live data, 2026-10-03): the **UOB** June 2026 pair (5 identical transactions, manual corrections on one copy), the **Trust Bank** June 2026 pair (8 identical transactions, different spellings of the bank name, manual corrections on the *other* copy), and two **CIMB** pairs that share one transaction each between one-transaction statements (not duplicates).

---

## Epic 14: Probable Duplicate Statement Detection

### US-14.1: A probable duplicate is skipped automatically, and I am told why
**As** the Account Owner, **I want** a statement that is really one I already have, saved as a different file, to be skipped automatically with the reason shown, **so that** my transactions and balances are never counted twice.

**Traces to**: FR-PD-1, FR-PD-2, FR-PD-3, FR-PD-4, NFR-PD-1, NFR-PD-6, A-PD-1, A-PD-2, A-PD-3, A-PD-7

**Acceptance Criteria**:
- *Happy path*: Given I already have a statement for a bank and period, When a different file with the same transactions (for example the same statement downloaded again) is ingested, Then it is skipped: no statement, transaction, or account is created from it, and the run results show **"probable duplicate of <statement>"** naming the statement it matches (its file name, bank, and period, A-PD-3) and the reason, for example "8 of 8 transactions match".
- *My real cases*: Given the UOB June 2026 pair and the Trust Bank June 2026 pair (whose two statements spell the bank name differently), When they are evaluated, Then both are recognized as probable duplicates (NFR-PD-1).
- *Wording tolerance*: Given the same PDF read twice produces slightly different wording on a few descriptions, When about 80% or more of the smaller statement's transactions still match on date, amount, direction, and description, Then it is still recognized (A-PD-2).
- *Not a duplicate*: Given a statement for the same bank but a different month, or one where fewer than about 80% of the transactions match, When it is ingested, Then it is ingested normally.
- *Small statements*: Given a statement with fewer than 3 transactions that matches another only on its transactions (my two CIMB look-alikes), When it is ingested, Then it is **not** flagged. Once the Account Balance backfill has run, a small statement is flagged only if its account identifier **and** closing balance and date also match (FR-PD-4).
- *Different accounts at one bank*: Given two statements from the same bank whose account identifiers are both known and differ, When their transactions happen to be similar, Then they are not flagged (A-PD-1). Where identifiers are not known (before the backfill), bank plus transactions is used.
- *Two new duplicates in one run*: Given two files in the same ingestion run that duplicate each other, When the run processes them, Then the first processed is ingested and the second is skipped as a probable duplicate of it (A-PD-7).
- *Exact copies unchanged*: Given a byte-identical file, When it is ingested, Then it is skipped before extraction exactly as it is today (NFR-PD-6).
- *No side effects*: Given a skipped file, When the run finishes, Then no account or statement section was created from it.

### US-14.2: I can see the evidence and be sure it really is a duplicate
**As** the Account Owner, **I want** to click "probable duplicate of <statement>" and see the two statements compared, **so that** I can be certain before I trust the skip.

**Traces to**: FR-PD-5, FR-PD-6, A-PD-3, NFR-PD-8

**Acceptance Criteria**:
- *Happy path*: Given a run result row "probable duplicate of <statement>", When I click it, Then I see the skipped file and the matched statement side by side, each with up to 10 transactions: **the 10 largest by amount, ties broken by earlier date**, plus the headline figures (transaction counts, periods, how many matched).
- *Markers*: Given the comparison, When I read it, Then each row is marked **"also on the other statement"** or **"only on this one"**, so I can see both what matches and what does not.
- *Fewer than 10*: Given a statement with 10 or fewer transactions, When I open the comparison, Then all of its transactions are shown.
- *Same rule on both sides*: Given the two lists, When I compare them, Then they were chosen by the same rule, so matching rows line up.
- *Still there later*: Given I open the comparison after the original statement has since been changed (a category corrected, or the statement removed), When it opens, Then it still shows what was compared at the time of detection.
- *Presentation*: Given light or dark mode on a phone or a desktop, When I use the comparison, Then it is legible and usable in each (NFR-PD-8).

### US-14.3: If it is not a duplicate, I can ingest it anyway
**As** the Account Owner, **I want** to override a skip, **so that** a legitimate statement wrongly flagged is never lost.

**Traces to**: FR-PD-7, A-PD-4, A-PD-8

**Acceptance Criteria**:
- *Happy path*: Given a skipped probable duplicate that I judge is not one, When I choose **"Not a duplicate — ingest it"** in the comparison view, Then the file is ingested on the **next** ingestion run (A-PD-4, not instantly), and the view shows it as waiting for the next run until then.
- *Remembered*: Given I have overridden a file, When later runs scan the folder, Then it is never flagged again, because the decision is remembered by the file's content (A-PD-8), so renaming or re-uploading the identical file does not bring the flag back.
- *The original is gone*: Given the statement it was matched against has since been removed, When the next run processes the file, Then it is no longer a duplicate of anything and is ingested normally.
- *After ingestion*: Given an overridden file has been ingested, When I look at the comparison, Then it shows that it was ingested at my request.

### US-14.4: A flagged or removed file is not re-read on every run
**As** the Account Owner, **I want** files that were flagged or removed to be recognized without being read again, **so that** I am not spending Gemini quota on the same file every run.

**Traces to**: FR-PD-8, FR-PD-13, NFR-PD-2, A-PD-8

**Acceptance Criteria**:
- *Happy path*: Given a file flagged on an earlier run that is still in my Drive folder, When a later run scans the folder, Then it is recognized from its content **before extraction**, skipped without a Gemini call, and still listed in that run's results with its reason and its comparison link.
- *Removed copy*: Given a duplicate I confirmed for removal (US-14.6) whose file is still in Drive, When later runs scan the folder, Then it is never re-ingested and never re-read.
- *Overridden file*: Given a file I overrode (US-14.3), When the next run scans the folder, Then it is ingested, not skipped.
- *Exact copies unchanged*: Given a byte-identical file, When a run scans it, Then it behaves as it does today.

### US-14.5: I can see duplicates already in my data and decide what to do
**As** the Account Owner, **I want** a list of duplicate pairs that are already in my data, **so that** I can clean them up on my own terms.

**Traces to**: FR-PD-9, FR-PD-10, FR-PD-11, A-PD-5, A-PD-6

**Acceptance Criteria**:
- *Happy path*: Given duplicate pairs already in my data (the UOB and Trust June pairs), When I open the Review page, Then a **"Probable duplicate statements"** panel lists each pair with the same comparison as US-14.2, the copy proposed to be **kept**, the copy proposed to be **removed**, and how many manual corrections each copy carries.
- *Badge*: Given pairs awaiting my decision, When I look at the navigation, Then a badge shows how many, the same way the other review flows do.
- *Which copy is proposed*: Given a pair, When the proposal is made, Then the kept copy is the one carrying manual corrections; if neither or both carry some, the earlier-ingested one (FR-PD-11).
- *Dismiss*: Given a pair I judge is not a duplicate, When I dismiss it, Then it leaves the panel and the badge and is never flagged again (A-PD-5).
- *No swap*: Given the proposal, When I disagree with which copy it would keep, Then there is no control to swap it; my choice is to dismiss the pair (A-PD-6).
- *Nothing happens on its own*: Given pairs in the panel, When I do nothing, Then nothing is removed or changed.
- *Small look-alikes*: Given my two CIMB one-transaction pairs, When the panel is built, Then they are not listed (FR-PD-4).
- *Empty state*: Given no pairs, When I open the Review page, Then there is no badge and the panel shows nothing to decide.

### US-14.6: Removing a confirmed duplicate is safe and complete
**As** the Account Owner, **I want** removal to be explicit, complete, and clear about what it deletes, **so that** a duplicate is truly gone and I do not lose work by accident.

**Traces to**: FR-PD-11, FR-PD-12, FR-PD-13, FR-PD-14, NFR-PD-3, NFR-PD-4

**Acceptance Criteria**:
- *Happy path*: Given a pair in the panel, When I confirm removal, Then the proposed duplicate statement is **permanently deleted** along with its transactions, everything depending on them (recategorization jobs and proposals, categorization disagreements, recurring-payment matches, and its account-section rows once the Account Balance feature is in place), and its embeddings in the vector store; the file in Drive is untouched.
- *The confirmation says exactly what will go*: Given the confirmation, When I read it, Then it states the number of transactions and the dependent rows that will be deleted.
- *Manual corrections*: Given only one copy carries manual corrections, When I confirm, Then that copy is the one kept and no corrections are lost. Given **both** copies carry some, When I read the confirmation, Then it states how many manual corrections on the removed copy will be lost (the earlier-ingested copy is kept, FR-PD-11).
- *All or nothing*: Given a removal that fails partway, When it ends, Then nothing was deleted, the panel shows it as failed with the reason, and I can retry.
- *Status*: Given I confirm, When the removal is carried out in the background by the Ingestion Worker (NFR-PD-4), Then the panel shows it as pending and then done or failed.
- *Remembered*: Given a removal completed, When later runs scan Drive, Then the removed copy's file is recognized and never re-ingested (US-14.4).
- *Numbers correct afterward*: Given a pair removed, When I look at the dashboards, Then the duplicated transactions (for example the 5 June UOB transactions) are no longer counted twice.

### US-14.7: The Account Balance backfill handles duplicates without losing my work
**As** the Account Owner, **I want** the backfill's re-read to resolve the duplicates it meets, **so that** it does not recreate them or lose the manual corrections that sat on a copy it skips.

**Traces to**: FR-PD-15, FR-PD-16, FR-PD-17, FR-PD-18, NFR-PD-5

**Acceptance Criteria**:
- *Dry run*: Given I start the backfill, When it prints its dry run, Then it lists the probable-duplicate pairs among my existing statements that it will skip, and which copy it will keep in each (FR-PD-11).
- *The right copy is kept*: Given a pair, When the reingest runs, Then the copy the rule (US-14.5) would keep is the one retained, and the other is skipped as a probable duplicate with its comparison recorded.
- *Corrections are carried across*: Given manual corrections sat on the copy that was skipped (as in both my pairs, where they sit on only one copy), When the backfill finishes, Then they are applied to the matching transactions of the kept copy and are not reported as unmatched merely because their copy was skipped.
- *The report*: Given the backfill completes, When I read the completion report, Then it lists the skipped duplicates and the corrections carried across.
- *A wrong skip is recoverable*: Given the backfill skipped a statement that was not a duplicate, When I open its comparison, Then I can override it (US-14.3), and the backup and restore remain available (NFR-PD-5).
- *Outcome for my data*: Given the UOB and Trust June pairs, When the backfill has finished, Then each month has one statement, with my manual corrections intact.
- *Sequencing (FR-PD-18)*: this feature is built and in place before the backfill is run; that is a project ordering constraint, not a user-visible behavior, and is enforced by the workflow plan.

---

## Amendments

**2026-10-04 (Ingestion Worker Functional Design, Question 1 = C; see the requirements amendment of the same date).** Added acceptance criteria:
- **US-14.1 — a larger file that contains a smaller held statement**: Given a new file that contains every transaction of a held statement and more, When it is ingested, Then it is still skipped as a probable duplicate, but the run result and the comparison say prominently that the file is the larger one and how many of its transactions have no match and were not ingested, so I can choose to override it.
- **US-14.5 — pairs of clearly different sizes**: Given two held statements where one wholly or largely contains the other and their sizes clearly differ, When I open the Review page, Then the pair is listed for information only, with its comparison and a dismiss action and **no remove action**, and it counts in the badge until I dismiss it.
- **US-14.6 — what the confirmation says**: Given a pair where removal is offered, When I read the confirmation, Then it also states how many transactions exist only on the copy that would be removed.
- **US-14.7 — the backfill and different sizes**: Given two existing statements of clearly different sizes, When the backfill runs, Then it does **not** skip either; both are re-ingested and the pair stays in the panel for information.

## Traceability Summary

| Story | Requirements Covered |
|---|---|
| US-14.1 | FR-PD-1, FR-PD-2, FR-PD-3, FR-PD-4, NFR-PD-1, NFR-PD-6, A-PD-1, A-PD-2, A-PD-3, A-PD-7 |
| US-14.2 | FR-PD-5, FR-PD-6, A-PD-3, NFR-PD-8 |
| US-14.3 | FR-PD-7, A-PD-4, A-PD-8 |
| US-14.4 | FR-PD-8, FR-PD-13, NFR-PD-2, A-PD-8 |
| US-14.5 | FR-PD-9, FR-PD-10, FR-PD-11, A-PD-5, A-PD-6 |
| US-14.6 | FR-PD-11, FR-PD-12, FR-PD-13, FR-PD-14, NFR-PD-3, NFR-PD-4 |
| US-14.7 | FR-PD-15, FR-PD-16, FR-PD-17, FR-PD-18, NFR-PD-5 |

Every FR-PD-1 through FR-PD-18 and A-PD-1 through A-PD-8 appears in at least one story. NFR-PD-7 (property-based and conventional tests) and the authentication part of NFR-PD-8 are cross-cutting implementation constraints reflected across the stories rather than stories of their own, the same treatment earlier epics gave their testing NFRs; the theme and responsive part of NFR-PD-8 is named in US-14.2.

## INVEST Check

- **Independent / Negotiable / Valuable / Testable**: all seven stories. Each delivers value to the Account Owner on its own, though US-14.2 and US-14.3 build on US-14.1's skip record, US-14.4 on both, and US-14.6 on US-14.5's panel; US-14.7 depends on the Account Balance backfill existing.
- **Small / Estimable**: US-14.1 to US-14.5 are each a single capability. **US-14.6 and US-14.7 are the largest**: US-14.6 spans a confirmation flow, a background removal that must also delete vectors and everything dependent on the transactions, and status reporting; US-14.7 changes the backfill's wipe-and-reingest ordering and its correction matching. They are kept whole because their parts only make sense together as one safe operation, but either may be split into smaller work items at Code Generation planning if its estimate proves too large.
