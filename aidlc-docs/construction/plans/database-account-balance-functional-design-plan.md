# Functional Design Plan — Database Unit: Account Balance at a Point in Time (Epic 13)

Unit: Database. Scope: two new entities for account identity (`Account`, `AccountKey`), one new entity for the manual anchor (`BalanceAnchor`), and three new columns on the existing `BankStatement` entity. Technology-agnostic: logical types only; exact column types, the migration, and indexes are Code Generation.

Please answer the one question at the bottom by filling in the letter after the `[Answer]:` tag. If none of the options fit, choose the last option (Other) and describe your preference. Let me know when you're done.

## Design decisions made and explained (not asked), with reasoning

Each follows from the approved requirements, stories, and Application Design, or from this project's existing data-model conventions, and has one defensible answer:

| Topic | Decision | Why this isn't a question |
|---|---|---|
| **Account fields** | `Account`: `id`, `name` (user-editable display name), `bank_name` (display, as first seen on a statement), `account_type` (`deposit` \| `credit_card` \| `unknown`), `type_user_set` (boolean, default false), `currency` (3-letter, fixed at creation), `created_at`, `updated_at`. | Direct translation of FR-AB-1/3/4, A-3, A-6. `type_user_set` is what lets the Account Resolver (Ingestion Worker) honor Application Design's rule that a user-corrected type is never overwritten by a later extraction. |
| **Account identity lives in a separate `AccountKey` entity, not on `Account`** | `AccountKey`: `id`, `account_id` (FK), `bank_key` (normalized bank name, computed by the application), `account_identifier` (nullable), `currency`. Uniqueness: at most one key per (`bank_key`, `account_identifier`, `currency`), with a missing identifier counting as its own distinct value. An account starts with one key; **merging re-points the absorbed account's keys to the survivor.** | **A gap found at this stage.** Without it, a merge fixes only past statements: the next statement printing the absorbed name (for example `OCBC Bank` after merging it into `OCBC`, or `POSB` after merging into `DBS`) would resolve to a brand-new account and undo the merge. Those exact fragmentations already exist in the live data. Keeping every key an account has ever been known by makes a merge permanent. Application Design's Account Management and Account Resolver components get a small dated addendum for this; no new component. |
| **Currency is part of the key** | The key is (`bank_key`, `account_identifier`, `currency`), not just (bank, identifier). | **Refines FR-AB-2.** Extraction always yields a currency (a statement without one cannot commit, WR-2), so it is always available. Including it means one account number holding balances in several currencies resolves to one account *per currency*, which is exactly what a per-currency balance needs, and means two statements can never be merged into an account of the wrong currency. A-6 (one currency per account) stays true by construction. A dated note is added to the requirements. |
| **One anchor per account, replaced in place** | `BalanceAnchor`: `id`, `account_id` (FK, unique), `balance` (decimal), `as_of_date`, `created_at`, `updated_at`. Replacing an anchor updates the row; no history is kept. | A-6 specifies one active anchor, replaceable. US-13.3 needs the *previous value shown before confirming*, not retained. The cross-check (FR-AB-8) is what catches a wrong anchor, and unlike `setting_changes` an anchor is not an audit-sensitive configuration change. Easy to extend later if you want history. |
| **Anchor survives a type change** | An account's anchor is kept, but ignored, while the account is not a deposit account. | Least destructive: if a type correction (US-13.2) is made by mistake, switching back restores the anchor instead of silently losing the number you typed. The Balance Component already only considers deposit accounts. |
| **`BankStatement` gains an account reference** | `account_id` (FK to `Account`), **nullable at the data level**. | Existing statements have no account until the backfill runs, and you may not run it the day this ships. New statements always get one (enforced by the Account Resolver, application layer). Tightening to required after the backfill would be a separate, later change. |
| **`BankStatement` gains the printed closing balance** | `closing_balance` (decimal, nullable) and `closing_balance_date` (date, nullable), **both present or both absent**. | FR-AB-5. A balance with no date, or a date with no balance, can't be cross-checked, so the pair is enforced together. |
| **No per-statement account type** | The as-extracted type is not stored on `BankStatement`; only `Account.account_type` exists. | Application Design left this open. A per-statement copy would be purely informational: nothing in the requirements or stories reads it, and the user-correctable value on `Account` is the one that matters. |
| **Anchor date not in the future** | Enforced by the application when an anchor is set, not as a database constraint. | "Not in the future" depends on today's date, which a constraint can't evaluate reliably; the project already enforces comparable time-relative rules at the application layer (for example BR-14..16). |
| **Deletion and referential behavior** | An account with statements cannot be deleted: statements must be re-pointed first. A merge re-points statements and keys, then deletes the emptied account and its anchor, handled as one unit by the Account Management Component. | Matches how the existing schema treats referenced rows (BR-1's reference integrity). Prevents orphaned statements. |
| **What the backfill wipes, keeps, and detaches** | Wiped: `bank_statements`, `transactions`, and rows depending on transactions (`recategorization_jobs`, `recategorization_proposals`, `categorization_disagreements`, `recurring_payment_matches`). **Kept: `accounts`, `account_keys`, `balance_anchors`**, so re-running the backfill never loses merges, names, types, or anchors. **Detached, not deleted:** `ingestion_run_files.bank_statement_id` (already nullable) is set to null so past run history survives. | FR-AB-17 listed what is discarded and preserved; this settles the three tables that did not exist when it was written and the one foreign key it did not mention. |
| **Cross-store consistency (flagged, not designed here)** | Wiping transactions leaves their embedding vectors behind in the vector store (Qdrant), keyed by transaction ids that no longer exist. The vector store client has no delete operation today. | Not a Database-unit concern, but it is a data fact the Database design exposes: handed to the Ingestion Worker's Functional Design (Backfill Tool), which must remove those points or the retroactive re-scan could match against ghosts. |

## Genuinely open question

### Question 1
Statements print an account number, and the new `account_identifier` is what lets the app tell two accounts at the same bank apart (Question 2 = A in the requirements). How much of the number should the app store and show?

A) Only the **last 4 digits** (the extraction prompt asks for just those). Less sensitive data in the database and on screen, and enough to tell accounts apart in almost every case; two accounts at the same bank sharing the same last 4 digits would be treated as one until you split them by renaming/merging.

B) The **account number as printed** on the statement (whatever the statement shows, full or already masked), normalized only for spacing and hyphens. Distinguishes accounts exactly, but stores your full account numbers in the database.

C) Other (please describe after [Answer]: tag below)

[Answer]:B

## Steps

- [x] `domain-entities.md`: add `Account`, `AccountKey`, and `BalanceAnchor` entities and the new `BankStatement` fields (with an addendum noting the key-based identity and the currency refinement); update the text entity-relationship diagram (width-verified).
- [x] `business-rules.md`: add **BR-30..BR-36** (account key uniqueness; currency fixed at creation; one anchor per account; closing balance and date together; user-set type is never overwritten; merge integrity and key re-pointing; backfill data handling), each marked DB-enforced or application-layer.
- [x] `business-logic-model.md`: add lifecycle/procedure sections: account creation and key lookup, merge (statements, keys, anchor choice, deletion), type correction and anchor retention, and the backfill's wipe/keep/detach rules including the flagged vector-store consequence.
- [x] Add dated addenda to `components.md` (Account Management, Account Resolver, Shared Data Store) and a refinement note to `account-balance-requirements.md` (FR-AB-2).
- [x] Validate against FR-AB-1..6, FR-AB-15..17, A-2, A-3, A-6, A-7 and US-13.1..13.3, 13.6, 13.7: every data need lands on an entity, field, or rule.
- [x] Update `aidlc-state.md`

## Mandatory Artifacts
- [x] `domain-entities.md`: updated in place
- [x] `business-rules.md`: updated in place (BR-30..BR-36)
- [x] `business-logic-model.md`: updated in place

## Amendment (2026-10-03) — several accounts per PDF

The Ingestion Worker's Functional Design clarification (Q1 = B) dropped the one-account-per-statement assumption this plan was built on. Consequences for this unit's design, recorded in `domain-entities.md`, `business-rules.md`, and `business-logic-model.md`: `BankStatement` no longer gains `account_id`, `closing_balance`, or `closing_balance_date`; a new **`StatementAccount`** entity (one row per account per statement, carrying the closing balance) takes them; `Transaction` gains a nullable `statement_account_id`; **BR-33** moves to `StatementAccount`; **BR-35** now also refuses to merge two accounts that appear together in a statement and re-points sections instead of statements; **BR-36**'s wipe order gains `statement_accounts` and now skips statements whose PDF is missing from Drive; new **BR-37** (an account appears at most once per statement) and **BR-38** (a transaction's section must belong to the transaction's own statement, a composite foreign key). Decisions in the table above that are unaffected: Account, AccountKey (currency in the key), BalanceAnchor, identifier stored as printed, and everything about anchors.
