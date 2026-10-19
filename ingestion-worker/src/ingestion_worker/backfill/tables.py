"""Table lists shared by the Backfill Tool (WR-54, WR-55; Database BR-36)."""

# Wipe order: each table depends on the ones after it, so rows go in this order.
WIPE_ORDER = (
    "recurring_payment_matches",
    "categorization_disagreements",
    "recategorization_proposals",
    "recategorization_jobs",
    "transactions",
    "statement_accounts",
    "bank_statements",
)

# Epic 14 (WR-69): the probable-duplicate tables the backfill MODIFIES (it adds remembered files,
# marks pairs superseded, and asks for a re-scan). They are never wiped (BR-50: they refer to
# statements by content hash, so nothing here depends on a statement row), but they are backed up
# so `restore` can put them back. Comparisons and their rows are NOT listed: they are write-once
# evidence that nothing deletes, so a comparison created after the backup simply stays.
DUPLICATE_TABLES = ("known_files", "duplicate_pairs", "statement_removal_jobs", "duplicate_scan_state")
# Replacing them on restore: children first, then parents (jobs -> pairs); inserts in the reverse order.
DUPLICATE_DELETE_ORDER = ("statement_removal_jobs", "duplicate_pairs", "known_files", "duplicate_scan_state")
DUPLICATE_INSERT_ORDER = ("duplicate_pairs", "statement_removal_jobs", "known_files", "duplicate_scan_state")

# Everything the wipe touches or modifies: the wipe set, plus ingestion_run_files, whose
# bank_statement_id link is detached (set null) rather than deleted, plus the Epic 14 tables above.
BACKED_UP_TABLES = (*WIPE_ORDER, "ingestion_run_files", *DUPLICATE_TABLES)

# Dependency order for inserting rows back on restore (parents before children).
RESTORE_INSERT_ORDER = (
    "bank_statements",
    "statement_accounts",
    "transactions",
    "recategorization_jobs",
    "recategorization_proposals",
    "categorization_disagreements",
    "recurring_payment_matches",
)

BACKUP_FOLDER_PREFIX = "pre-backfill-"
MANIFEST_FILE = "manifest.json"
