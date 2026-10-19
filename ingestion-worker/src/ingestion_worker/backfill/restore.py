"""`restore` (WR-54): put the backed-up tables back exactly as they were when the backup
was taken. Verified against the manifest before anything is deleted; one transaction;
then every restored transaction is queued for re-embedding (their vectors were wiped)."""

import json
import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion_worker.backfill.export import BackupArtifact, read_rows
from ingestion_worker.backfill.service import (
    BackfillRefused,
    recreate_vector_collection,
)
from ingestion_worker.backfill.tables import (
    DUPLICATE_DELETE_ORDER,
    DUPLICATE_INSERT_ORDER,
    RESTORE_INSERT_ORDER,
    WIPE_ORDER,
)

logger = logging.getLogger(__name__)

_CHUNK = 500


def restore_backup(
    db: Session, artifact: BackupArtifact, *, confirm: Callable[[str], str], folder_name: str,
    out: Callable[[str], None] = print,
) -> dict[str, int]:
    manifest = artifact.manifest
    # Epic 14 (WR-69): a backup taken before this feature has no probable-duplicate tables; those are
    # then left exactly as they are. Comparisons are never replaced: they are write-once evidence that
    # nothing deletes, so one created after the backup simply stays.
    duplicate_delete = [t for t in DUPLICATE_DELETE_ORDER if t in manifest["tables"]]
    duplicate_insert = [t for t in DUPLICATE_INSERT_ORDER if t in manifest["tables"]]
    summary = ", ".join(f"{t}: {manifest['tables'][t]['row_count']}" for t in (*RESTORE_INSERT_ORDER, *duplicate_insert))
    out(f"This will REPLACE the current contents of these tables with the backup taken at {manifest['created_at']}: {summary}")
    out("Anything ingested or changed since that backup in those tables will be lost.")
    phrase = f"RESTORE FROM {folder_name}"
    if confirm(f"To proceed, type exactly: {phrase}\n> ").strip() != phrase:
        raise BackfillRefused("confirmation did not match; NOTHING was changed.")

    # Detach every run-file link first: the reingest's run files point at statements this
    # restore is about to delete. The backed-up links are re-attached at the end.
    db.execute(text("UPDATE ingestion_run_files SET bank_statement_id = NULL"))
    for table in WIPE_ORDER:  # same dependency order as the wipe
        db.execute(text(f'DELETE FROM "{table}"'))
    for table in duplicate_delete:  # jobs before pairs; none of these refers to a statement row (BR-50)
        db.execute(text(f'DELETE FROM "{table}"'))
    restored: dict[str, int] = {}
    for table in (*RESTORE_INSERT_ORDER, *duplicate_insert):
        rows = read_rows(artifact, table)
        for start in range(0, len(rows), _CHUNK):
            chunk = json.dumps(rows[start:start + _CHUNK], default=str)
            db.execute(
                text(f'INSERT INTO "{table}" SELECT * FROM jsonb_populate_recordset(NULL::"{table}", CAST(:rows AS jsonb))'),
                {"rows": chunk},
            )
        restored[table] = len(rows)
    links = [
        {"id": row["id"], "bank_statement_id": row["bank_statement_id"]}
        for row in read_rows(artifact, "ingestion_run_files")
        if row["bank_statement_id"] is not None
    ]
    for start in range(0, len(links), _CHUNK):
        db.execute(
            text(
                "UPDATE ingestion_run_files f SET bank_statement_id = r.bank_statement_id "
                "FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS r(id uuid, bank_statement_id uuid) WHERE f.id = r.id"
            ),
            {"rows": json.dumps(links[start:start + _CHUNK])},
        )
    db.execute(text("UPDATE transactions SET embedding_status = 'pending'"))
    db.commit()
    out(f"Restored: {restored}. Recreating the vector collection so the restored transactions are re-embedded.")
    recreate_vector_collection()
    return restored
