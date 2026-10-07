"""WR-68 / BR-51: the shared delete helper. The Backfill Tool's own tests (unchanged) prove the
move was behaviour-neutral; these prove what a removal needs on top: the removed transaction ids
are returned, scoping is exact, and nothing the new tables or accounts hold is touched."""

from backfill_helpers import FakeDrive, seed_legacy
from duplicates_helpers import june, make_statement
from sqlalchemy import text
from transactagent_db.models import (
    Account,
    BankStatement,
    IngestionRunFile,
    StatementAccount,
    Transaction,
)

from ingestion_worker.duplicates.cascade import delete_statements


def _count(db, table):
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


class TestDeleteStatements:
    def test_deletes_one_statement_and_everything_depending_on_it_with_exact_counts(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        s1_txn_ids = sorted(str(t.id) for t in (seed.ntuc, seed.coffee, seed.mrt_manual, seed.mrt_auto))

        result = delete_statements(db_session, [str(seed.s1.id)])

        assert result.transaction_ids == s1_txn_ids  # captured before the delete
        assert result.counts == {
            "ingestion_run_files_detached": 1,
            "recurring_payment_matches": 1,
            "categorization_disagreements": 1,
            "recategorization_proposals": 2,  # one by candidate, one by the source job
            "recategorization_jobs": 1,
            "transactions": 4,
            "statement_accounts": 0,
            "bank_statements": 1,
        }

    def test_other_statements_and_their_dependents_are_untouched(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())

        delete_statements(db_session, [str(seed.s1.id)])

        assert db_session.get(BankStatement, seed.s2.id) is not None
        assert db_session.get(BankStatement, seed.s3.id) is not None
        assert db_session.get(Transaction, seed.salary.id) is not None
        assert db_session.get(Transaction, seed.gone.id) is not None
        assert _count(db_session, "recurring_payment_matches") == 1  # the kept statement's match survives
        assert _count(db_session, "categorization_disagreements") == 1

    def test_run_files_are_detached_not_deleted(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())

        delete_statements(db_session, [str(seed.s1.id)])
        db_session.expire_all()  # the helper writes with raw SQL, so the ORM's copy is stale

        run_file = db_session.get(IngestionRunFile, seed.run_file.id)
        assert run_file is not None and run_file.bank_statement_id is None

    def test_sections_go_but_the_account_survives(self, db_session):
        statement = make_statement(db_session, h="1" * 64, rows=june(3), accounts=[("1234", "SGD", None, None)])
        account_id = db_session.query(StatementAccount).one().account_id

        result = delete_statements(db_session, [str(statement.id)])

        assert result.counts["statement_accounts"] == 1 and result.counts["transactions"] == 3
        assert db_session.get(Account, account_id) is not None  # a removal never loses an account or its anchor

    def test_an_empty_list_deletes_nothing(self, db_session):
        seed_legacy(db_session, FakeDrive())
        before = _count(db_session, "bank_statements")

        result = delete_statements(db_session, [])

        assert result.transaction_ids == [] and _count(db_session, "bank_statements") == before

    def test_it_never_commits(self, db_session, monkeypatch):
        """The caller owns the transaction (a removal needs the delete and its bookkeeping to commit
        together, BR-46), so the helper must not commit or roll back on its own."""
        seed = seed_legacy(db_session, FakeDrive())

        def forbidden(*_args, **_kwargs):
            raise AssertionError("delete_statements must not commit or roll back")

        monkeypatch.setattr(db_session, "commit", forbidden)
        monkeypatch.setattr(db_session, "rollback", forbidden)

        delete_statements(db_session, [str(seed.s1.id)])  # no error: it only flushed/executed in the caller's transaction
