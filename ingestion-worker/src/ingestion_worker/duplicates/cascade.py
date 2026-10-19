"""The one implementation of "delete statements and everything that depends on them" (WR-68, BR-51).

Used by the Backfill Tool's wipe and by the Statement Removal Handler, so the dependents list
exists exactly once in this unit. (The Database unit's guard test fails if a table gains a foreign
key to a statement table without being added to the set of known dependents; the API Service's
removal preview is the third place that must agree.)

Runs in the CALLER's transaction and never commits.
"""

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

# SQL fragments over a statement-id list bound as `:ids`.
IDS_SQL = "CAST(:ids AS uuid[])"
TXN_IDS_SQL = f"(SELECT id FROM transactions WHERE bank_statement_id = ANY({IDS_SQL}))"
JOB_IDS_SQL = f"(SELECT id FROM recategorization_jobs WHERE source_transaction_id IN {TXN_IDS_SQL})"


@dataclass
class DeleteResult:
    """What was removed. `transaction_ids` is captured BEFORE the delete: once the rows are gone
    their ids can no longer be looked up, and the embeddings still need deleting (BR-46)."""

    transaction_ids: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def delete_statements(db: Session, statement_ids: list[str]) -> DeleteResult:
    """BR-36 order: detach run files, then rows that depend on a transaction, then the
    transactions, their sections, and the statements. Scoped to `statement_ids`, so a statement
    that is not listed (and everything depending on it) is untouched. `accounts`, `account_keys`,
    `balance_anchors` and every Epic 14 table are never touched (BR-50)."""
    ids = [str(i) for i in statement_ids]
    result = DeleteResult(
        transaction_ids=[
            str(row)
            for row in db.execute(text(f"SELECT id FROM transactions WHERE bank_statement_id = ANY({IDS_SQL}) ORDER BY id"), {"ids": ids}).scalars()
        ]
    )

    def run(label: str, sql: str) -> None:
        result.counts[label] = db.execute(text(sql), {"ids": ids}).rowcount

    run("ingestion_run_files_detached", f"UPDATE ingestion_run_files SET bank_statement_id = NULL WHERE bank_statement_id = ANY({IDS_SQL})")
    run("recurring_payment_matches", f"DELETE FROM recurring_payment_matches WHERE transaction_id IN {TXN_IDS_SQL}")
    run("categorization_disagreements", f"DELETE FROM categorization_disagreements WHERE transaction_id IN {TXN_IDS_SQL}")
    run(
        "recategorization_proposals",
        f"DELETE FROM recategorization_proposals WHERE candidate_transaction_id IN {TXN_IDS_SQL} "
        f"OR recategorization_job_id IN {JOB_IDS_SQL}",
    )
    run("recategorization_jobs", f"DELETE FROM recategorization_jobs WHERE source_transaction_id IN {TXN_IDS_SQL}")
    run("transactions", f"DELETE FROM transactions WHERE bank_statement_id = ANY({IDS_SQL})")
    run("statement_accounts", f"DELETE FROM statement_accounts WHERE bank_statement_id = ANY({IDS_SQL})")
    run("bank_statements", f"DELETE FROM bank_statements WHERE id = ANY({IDS_SQL})")
    return result
