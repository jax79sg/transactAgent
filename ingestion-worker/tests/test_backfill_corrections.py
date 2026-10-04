"""Preserving manual corrections (WR-55): captured from the backup artifact, re-applied by
multiset matching on (content hash, date, amount, direction, description)."""

from datetime import date

from backfill_helpers import FakeDrive, add_txn, seed_legacy, sha256
from sqlalchemy import text
from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    RecategorizationJob,
)

from ingestion_worker.backfill import corrections, export


def _artifact(db_session, seed, wipe_ids):
    return export.build_backup(db_session.connection(), extra_manifest={"wipe_set_statement_ids": [str(i) for i in wipe_ids]})


def _category(db, name):
    return db.query(Category).filter_by(name=name).one()


class TestCapture:
    def test_only_manual_corrections_of_wiped_statements_are_captured(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])  # s3 (the kept one) is not in the wipe set

        captured = corrections.capture_corrections(artifact)

        assert sorted((c.description, c.direction) for c in captured) == [("MRT", "out"), ("NTUC", "out"), ("SALARY", "in")]
        ntuc = next(c for c in captured if c.description == "NTUC")
        assert (ntuc.statement_content_hash, ntuc.transaction_date, str(ntuc.amount)) == (sha256(b"PDF-ONE"), "2026-01-15", "25.50")
        assert ntuc.category_id == str(seed.categories.dining.id)

    def test_a_kept_statements_corrections_are_never_captured(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])

        assert all(c.description != "GONE" for c in corrections.capture_corrections(artifact))


class TestApply:
    def _reingested(self, db, seed, *, mrt_rows=2, with_salary=True):
        """What the reingest produces: the same statements, fresh transaction rows with the
        pipeline's own (non-manual) categories."""
        groceries = _category(db, "Groceries")
        for table in (
            "recurring_payment_matches", "categorization_disagreements", "recategorization_proposals",
            "recategorization_jobs", "transactions",
        ):
            db.execute(text(f"DELETE FROM {table}"))
        s1, s2 = db.get(BankStatement, seed.s1.id), db.get(BankStatement, seed.s2.id)
        add_txn(db, s1, groceries, "NTUC", date(2026, 1, 15), "25.50")
        add_txn(db, s1, groceries, "COFFEE", date(2026, 1, 16), "4.50")
        for _ in range(mrt_rows):
            add_txn(db, s1, groceries, "MRT", date(2026, 1, 17), "2.00")
        if with_salary:
            add_txn(db, s2, groceries, "SALARY", date(2026, 2, 1), "3000", direction="in")

    def _apply(self, db, seed):
        artifact = _artifact(db, seed, [seed.s1.id, seed.s2.id])
        captured = corrections.capture_corrections(artifact)
        self._reingested(db, seed)
        return captured

    def test_matching_rows_get_their_manual_category_back(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._apply(db_session, seed)

        result = corrections.apply_corrections(db_session, captured)

        assert (result.captured, result.applied, result.already_applied, result.unmatched) == (3, 3, 0, [])
        dining = _category(db_session, "Dining")
        rows = db_session.execute(text("SELECT description, category_id, category_source::text FROM transactions ORDER BY description, created_at, id")).all()
        manual = {r.description for r in rows if r.category_source == "manual"}
        assert manual == {"NTUC", "MRT", "SALARY"} and all(r.category_id == dining.id for r in rows if r.category_source == "manual")
        assert next(r for r in rows if r.description == "COFFEE").category_source != "manual"  # untouched

    def test_identical_rows_are_a_multiset_one_captured_correction_hits_exactly_one_of_two(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._apply(db_session, seed)

        corrections.apply_corrections(db_session, captured)

        mrt = db_session.execute(text("SELECT category_source::text AS s FROM transactions WHERE description = 'MRT'")).all()
        assert sorted(r.s for r in mrt).count("manual") == 1 and len(mrt) == 2

    def test_a_correction_with_no_matching_row_is_reported_not_dropped(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])
        captured = corrections.capture_corrections(artifact)
        self._reingested(db_session, seed, with_salary=False)  # the reingest did not produce SALARY

        result = corrections.apply_corrections(db_session, captured)

        assert result.applied == 2 and [u.description for u in result.unmatched] == ["SALARY"]

    def test_more_corrections_than_rows_reports_the_surplus(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        extra = add_txn(db_session, db_session.get(BankStatement, seed.s1.id), seed.categories.dining, "MRT", date(2026, 1, 17), "2.00", source=CategorySource.MANUAL)
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])
        captured = corrections.capture_corrections(artifact)
        assert sum(c.description == "MRT" for c in captured) == 2 and extra is not None
        self._reingested(db_session, seed, mrt_rows=1)  # only one MRT row came back

        result = corrections.apply_corrections(db_session, captured)

        assert [u.description for u in result.unmatched] == ["MRT"]

    def test_direction_distinguishes_otherwise_identical_rows(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])
        captured = corrections.capture_corrections(artifact)
        self._reingested(db_session, seed, with_salary=False)
        add_txn(db_session, db_session.get(BankStatement, seed.s2.id), _category(db_session, "Groceries"), "SALARY", date(2026, 2, 1), "3000", direction="out")

        result = corrections.apply_corrections(db_session, captured)

        assert [u.description for u in result.unmatched] == ["SALARY"]  # the OUT row is not the IN correction's match

    def test_applying_twice_changes_nothing_the_second_time(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._apply(db_session, seed)
        corrections.apply_corrections(db_session, captured)

        again = corrections.apply_corrections(db_session, captured)

        assert (again.applied, again.already_applied, again.unmatched) == (0, 3, [])

    def test_no_recategorization_jobs_are_created(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._apply(db_session, seed)

        corrections.apply_corrections(db_session, captured)

        assert db_session.query(RecategorizationJob).count() == 0  # _reingested cleared them; applying adds none
