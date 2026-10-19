"""Preserving manual corrections (WR-55): captured from the backup artifact, re-applied by
multiset matching on (content hash, date, amount, direction, description)."""

from dataclasses import replace
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


class TestApplyToRereadDescriptions:
    """The model does not return word-for-word identical text on a second extraction (found by
    `check-extraction` on the real statements): line breaks where the stored text has spaces, and small OCR
    differences. Whitespace is compared collapsed; a strict fallback covers the rest."""

    def _captured_and_reingested(self, db, seed):
        helper = TestApply()
        return helper._apply(db, seed)

    def _row(self, db, description):
        return db.execute(text("SELECT id, category_source::text AS s, category_id FROM transactions WHERE description = :d"), {"d": description}).one()

    def test_a_line_break_where_the_stored_text_has_a_space_is_the_same_description(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        # the stored correction read "NTUC FAIRPRICE"; the re-read row reads "NTUC\nFAIRPRICE"
        captured = [replace(c, description="NTUC FAIRPRICE") if c.description == "NTUC" else c for c in captured]
        db_session.execute(text("UPDATE transactions SET description = E'NTUC\\nFAIRPRICE' WHERE description = 'NTUC'"))

        result = corrections.apply_corrections(db_session, captured)

        assert result.unmatched == [] and result.applied == 3
        assert result.loosely_placed == []  # an exact (whitespace-insensitive) match, not the fallback
        assert db_session.execute(text("SELECT category_source::text FROM transactions WHERE description LIKE 'NTUC%'")).scalar_one() == "manual"

    def test_a_stored_description_that_itself_has_a_line_break_still_matches_an_identical_reread(self, db_session):
        """142 stored descriptions on the real data contain a line break. The captured side must be collapsed
        too, or an IDENTICAL re-read (which the exact match used to find) would stop matching."""
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        captured = [replace(c, description="NTUC\nFAIRPRICE") if c.description == "NTUC" else c for c in captured]
        db_session.execute(text("UPDATE transactions SET description = E'NTUC\\nFAIRPRICE' WHERE description = 'NTUC'"))

        result = corrections.apply_corrections(db_session, captured)

        assert result.unmatched == [] and result.applied == 3 and result.loosely_placed == []

    def test_tabs_runs_of_spaces_and_edges_are_whitespace_too(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = E'  NTUC\\t \\n' WHERE description = 'NTUC'"))

        result = corrections.apply_corrections(db_session, captured)

        assert result.unmatched == [] and result.loosely_placed == []

    def test_a_small_ocr_difference_is_placed_by_date_and_amount_and_reported(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN' WHERE description = 'SALARY'"))

        result = corrections.apply_corrections(db_session, captured)

        assert result.unmatched == [] and result.applied == 3
        (placed,) = result.loosely_placed
        assert (placed.correction.description, placed.new_description) == ("SALARY", "SALARY - JAN")
        assert self._row(db_session, "SALARY - JAN").s == "manual"

    def test_applying_twice_is_still_idempotent_with_a_fallback_placement(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN' WHERE description = 'SALARY'"))
        corrections.apply_corrections(db_session, captured)

        again = corrections.apply_corrections(db_session, captured)

        assert (again.applied, again.unmatched) == (0, []) and again.already_applied == 3  # not suddenly UNMATCHED
        assert len(again.loosely_placed) == 1

    def test_two_candidate_rows_are_too_ambiguous_so_it_stays_unmatched(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN' WHERE description = 'SALARY'"))
        add_txn(db_session, db_session.get(BankStatement, seed.s2.id), _category(db_session, "Groceries"), "BONUS", date(2026, 2, 1), "3000", direction="in")

        result = corrections.apply_corrections(db_session, captured)

        assert [u.description for u in result.unmatched] == ["SALARY"] and result.loosely_placed == []
        assert self._row(db_session, "SALARY - JAN").s != "manual" and self._row(db_session, "BONUS").s != "manual"  # nothing guessed

    def test_a_row_with_a_different_manual_correction_is_never_overwritten(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN' WHERE description = 'SALARY'"))
        other = _category(db_session, "Groceries")
        db_session.execute(text("UPDATE transactions SET category_source = 'manual', category_id = :c WHERE description = 'SALARY - JAN'"), {"c": other.id})

        result = corrections.apply_corrections(db_session, captured)

        assert [u.description for u in result.unmatched] == ["SALARY"] and result.loosely_placed == []
        assert self._row(db_session, "SALARY - JAN").category_id == other.id  # the user's other correction survives

    def test_two_leftover_corrections_competing_for_two_free_rows_are_not_paired_by_guesswork(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        statement = db_session.get(BankStatement, seed.s2.id)
        dining = _category(db_session, "Dining")
        # two corrected rows in one slot whose re-read descriptions both changed, in either order
        corrected = [replace(c, description="SALARY") for c in captured if c.description == "SALARY"]
        extra = replace(corrected[0], description="BONUS", category_id=str(dining.id))
        db_session.execute(text("UPDATE transactions SET description = 'SALARY X' WHERE description = 'SALARY'"))
        add_txn(db_session, statement, _category(db_session, "Groceries"), "BONUS Y", date(2026, 2, 1), "3000", direction="in")

        result = corrections.apply_corrections(db_session, [c for c in captured if c.description != "SALARY"] + corrected + [extra])

        assert sorted(u.description for u in result.unmatched) == ["BONUS", "SALARY"] and result.loosely_placed == []

    def test_a_different_date_or_amount_or_direction_is_never_a_match(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        captured = self._captured_and_reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN', transaction_date = '2026-02-02' WHERE description = 'SALARY'"))

        result = corrections.apply_corrections(db_session, captured)

        assert [u.description for u in result.unmatched] == ["SALARY"] and result.loosely_placed == []

    def test_the_report_lists_every_fallback_placement_with_both_descriptions(self, db_session):
        seed = seed_legacy(db_session, FakeDrive())
        artifact = _artifact(db_session, seed, [seed.s1.id, seed.s2.id])
        captured = corrections.capture_corrections(artifact)
        TestApply()._reingested(db_session, seed)
        db_session.execute(text("UPDATE transactions SET description = 'SALARY - JAN' WHERE description = 'SALARY'"))
        result = corrections.apply_corrections(db_session, captured)

        from ingestion_worker.backfill import report

        data = report.build_report(db_session, artifact, result, [])
        rendered = report.render_report(data)

        (entry,) = data["manual_corrections"]["placed_by_date_and_amount"]
        assert (entry["description"], entry["new_description"]) == ("SALARY", "SALARY - JAN")
        assert "'SALARY' -> 'SALARY - JAN'" in rendered and "check by eye" in rendered
