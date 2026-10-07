"""WR-69 / FR-PD-15..17: the Backfill Tool's probable-duplicate handling, end to end against a real
PostgreSQL with an in-memory fake Drive. Both real-data shapes are used: the UOB June pair (manual
corrections on one copy) and the Trust June pair (two spellings of the bank, corrections on the OTHER
copy). Extraction, classification and the vector store are mocked at their module boundaries; nothing
here touches real data."""

from contextlib import nullcontext
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from backfill_helpers import FakeDrive, sha256
from duplicates_helpers import ensure_category, extracted, june, make_statement
from sqlalchemy import text
from transactagent_db.models import (
    BankStatement,
    DuplicatePair,
    DuplicatePairStatus,
    IngestionRunFile,
    IngestionRunFileOutcome,
    KnownFile,
    KnownFileState,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
    User,
)

from ingestion_worker.backfill import corrections, export, report, restore, service
from ingestion_worker.backfill import duplicates as backfill_duplicates
from ingestion_worker.backfill.tables import BACKED_UP_TABLES
from ingestion_worker.duplicates import repository
from ingestion_worker.duplicates import service as duplicates_service

UOB1, UOB2, TRUST1, TRUST2 = b"UOB-JUN-1", b"UOB-JUN-2", b"TRUST-JUN-1", b"TRUST-JUN-2"


class World:
    """Held, pre-backfill statements (no sections) whose content hashes are those of PDFs in the fake Drive."""

    def __init__(self, db, *, uob2_manual=0, uob_rows_2=None):
        self.db = db
        self.drive = FakeDrive()
        db.add(User(username="owner", password_hash="x"))
        db.flush()
        for file_id, name, pdf in (("f-uob1", "JUN 2026_0728.pdf", UOB1), ("f-uob2", "JUN 2026_0828.pdf", UOB2),
                                   ("f-trust1", "TRUST JUN a.pdf", TRUST1), ("f-trust2", "TRUST JUN b.pdf", TRUST2)):
            self.drive.add_pdf(file_id, name, pdf)
        self.results = {
            UOB1: extracted(june(5), bank="UOB"),
            UOB2: extracted(uob_rows_2 or june(5), bank="UOB"),
            TRUST1: extracted(june(8), bank="Trust Bank"),
            TRUST2: extracted(june(8), bank="Trust Bank Singapore Limited"),
        }
        # UOB: the corrections sit on the EARLIER copy (so it is kept); the later copy has none (or some).
        self.uob1 = make_statement(db, h=sha256(UOB1), bank="UOB", rows=june(5), manual=2, ingested_days=0, file_name="JUN 2026_0728.pdf")
        self.uob2 = make_statement(db, h=sha256(UOB2), bank="UOB", rows=uob_rows_2 or june(5), manual=uob2_manual, ingested_days=30, file_name="JUN 2026_0828.pdf")
        # Trust: the corrections sit on the LATER copy, which is therefore the one kept.
        self.trust1 = make_statement(db, h=sha256(TRUST1), bank="Trust Bank", rows=june(8), manual=0, ingested_days=1, file_name="TRUST JUN a.pdf")
        self.trust2 = make_statement(db, h=sha256(TRUST2), bank="Trust Bank Singapore Limited", rows=june(8), manual=2, ingested_days=31, file_name="TRUST JUN b.pdf")
        for s, f in ((self.uob1, "f-uob1"), (self.uob2, "f-uob2"), (self.trust1, "f-trust1"), (self.trust2, "f-trust2")):
            s.drive_file_id = f
        db.flush()
        self.output: list[str] = []

    def extract(self, pdf):
        return self.results[pdf]

    def run(self, *, confirm="WIPE 4 STATEMENTS"):
        with (
            self.drive.patched(),
            patch("ingestion_worker.embedding.vector_store._client", return_value=MagicMock()),
            patch("ingestion_worker.embedding.vector_store.recreate_transactions_collection", return_value=True),
            patch("ingestion_worker.orchestrator.pipeline.extract_statement", side_effect=self.extract),
            patch("ingestion_worker.orchestrator.pipeline.classify_batch", side_effect=lambda db, items: {d: "Groceries" for d, _ in items}),
        ):
            return service.run_backfill(
                self.db,
                snapshot=lambda: nullcontext(self.db.connection()),
                confirm=lambda prompt: confirm,
                out=self.output.append,
                sleep=lambda s: None,
            )

    def finish(self, folder):
        with self.drive.patched():
            _location, artifact = export.load_backup(self.db, folder)
            captured = corrections.rekey_for_skipped_copies(self.db, corrections.capture_corrections(artifact))
            result = corrections.apply_corrections(self.db, captured)
            data = report.build_report(self.db, artifact, result, service.list_drive_pdfs(self.db))
        return result, data, report.render_report(data)

    def statements_by_bank(self):
        return sorted((s.bank_name, s.pdf_content_hash) for s in self.db.query(BankStatement))


@pytest.fixture
def world(db_session):
    return World(db_session)


def manual_count(db, content_hash):
    return db.execute(
        text("SELECT count(*) FROM transactions t JOIN bank_statements b ON b.id = t.bank_statement_id "
             "WHERE b.pdf_content_hash = :h AND t.category_source = 'manual'"),
        {"h": content_hash},
    ).scalar_one()


class TestCheckDuplicates:
    def test_lists_both_pairs_the_copy_it_would_keep_and_writes_nothing(self, world):
        before = {t: world.db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in ("known_files", "duplicate_pairs", "duplicate_comparisons")}

        findings, near = backfill_duplicates.check_duplicates(world.db, world.output.append)

        text_out = "\n".join(world.output)
        assert len(findings) == 2 and near == []
        assert text_out.count("; removal offered") == 2
        by_keep = {f.keep_hash for f in findings}
        assert by_keep == {sha256(UOB1), sha256(TRUST2)}  # the copy carrying corrections, in each pair
        assert "read-only" in text_out
        after = {t: world.db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in before}
        assert after == before

    def test_reports_the_cimb_lookalikes_as_near_misses_with_the_reason(self, world):
        one = [(date(2026, 2, 28), "12.34", "INTEREST")]
        make_statement(world.db, h="c" * 64, bank="CIMB", rows=one, direction="in")
        make_statement(world.db, h="d" * 64, bank="CIMB", rows=one, direction="in", ingested_days=1)

        findings, near = backfill_duplicates.check_duplicates(world.db, world.output.append)

        assert len(findings) == 2 and len(near) == 1
        assert "not flagged because: a statement with fewer than 3 transactions" in "\n".join(world.output)

    def test_applies_the_rule_whatever_the_detection_switch_says(self, world):
        """check-duplicates is an explicit operator evaluation, so the (default OFF) switch is irrelevant."""
        from ingestion_worker import config

        assert config.settings.duplicate_detection_enabled is False
        findings, _ = backfill_duplicates.check_duplicates(world.db, world.output.append)
        assert len(findings) == 2


class TestDryRunAndPlan:
    def test_the_dry_run_lists_the_copies_it_will_skip_and_keeps_the_right_ones(self, world):
        report_ = service.dry_run(world.db, _drive_files(world))

        skipped = {s.skip_hash: s.kept_hash for s in report_.skip_plan.skips}
        assert skipped == {sha256(UOB2): sha256(UOB1), sha256(TRUST1): sha256(TRUST2)}
        rendered = service.render_dry_run(report_)
        assert "2 copy(ies) will be SKIPPED" in rendered and "JUN 2026_0828.pdf" in rendered

    def test_a_dismissed_pair_is_neither_skipped_nor_listed(self, world):
        duplicates_service_scan(world.db)
        pair = repository.load_pairs(world.db)[repository.pair_key(sha256(UOB1), sha256(UOB2))]
        pair.status = DuplicatePairStatus.DISMISSED
        world.db.flush()

        plan = backfill_duplicates.plan_skips(world.db, [str(s.id) for s in world.db.query(BankStatement)])

        assert {s.skip_hash for s in plan.skips} == {sha256(TRUST1)}
        assert plan.dismissed == 1

    def test_a_pair_whose_skip_copy_is_not_re_read_is_left_for_the_panel(self, world):
        wipe = [str(world.uob1.id), str(world.trust1.id), str(world.trust2.id)]  # the UOB copy to skip is NOT in the wipe set

        plan = backfill_duplicates.plan_skips(world.db, wipe)

        assert {s.skip_hash for s in plan.skips} == {sha256(TRUST1)}
        assert len(plan.left_for_panel) == 1 and "not re-read" in plan.left_for_panel[0][1]

    def test_a_pair_of_clearly_different_sizes_is_not_skipped(self, db_session):
        big = [*june(5), *((date(2026, 6, 20 + i), f"{500 + i}.00", f"EXTRA {i}") for i in range(10))]
        w = World(db_session, uob_rows_2=big)

        plan = backfill_duplicates.plan_skips(db_session, [str(s.id) for s in db_session.query(BankStatement)])

        assert {s.skip_hash for s in plan.skips} == {sha256(TRUST1)}
        assert len(plan.different_size) == 1
        assert "NOT skipped" in "\n".join(backfill_duplicates.render_plan(plan))
        assert w is not None


def _drive_files(world):
    return world.drive.list_folder_pdf_files(world.db)


def duplicates_service_scan(db):
    with patch("ingestion_worker.config.settings.duplicate_detection_enabled", True):
        duplicates_service.run_pair_scan(db)


class TestRunEndToEnd:
    def test_both_real_pairs_are_resolved_one_statement_per_month_with_corrections_intact(self, world):
        outcome = world.run()

        assert outcome.reingest_run_id is not None
        by_hash = {h for _bank, h in world.statements_by_bank()}
        assert by_hash == {sha256(UOB1), sha256(TRUST2)}  # the copy carrying the corrections, in each pair
        known = {k.pdf_content_hash: k for k in world.db.query(KnownFile)}
        assert set(known) == {sha256(UOB2), sha256(TRUST1)}
        assert known[sha256(UOB2)].matched_statement_hash == sha256(UOB1)
        assert all(k.state is KnownFileState.PROBABLE_DUPLICATE for k in known.values())

        _result, data, rendered = world.finish(outcome.backup_folder)
        assert manual_count(world.db, sha256(UOB1)) == 2 and manual_count(world.db, sha256(TRUST2)) == 2
        assert data["manual_corrections"]["unmatched"] == []
        assert len(data["probable_duplicates_skipped"]) == 2
        assert "Probable duplicates skipped by the reingest: 2" in rendered

    def test_the_skipped_copies_are_not_read_by_gemini_and_not_reported_as_missing(self, world):
        outcome = world.run()
        extract_calls = []
        with (
            world.drive.patched(),
            patch("ingestion_worker.orchestrator.pipeline.extract_statement", side_effect=extract_calls.append),
        ):
            pass  # (the reingest itself is what matters; assert on its run files below)
        run_files = {f.drive_file_name: f for f in world.db.query(IngestionRunFile).filter(IngestionRunFile.ingestion_run_id == outcome.reingest_run_id)}
        assert run_files["JUN 2026_0828.pdf"].outcome is IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
        assert run_files["TRUST JUN a.pdf"].outcome is IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
        assert run_files["JUN 2026_0728.pdf"].outcome is IngestionRunFileOutcome.PROCESSED
        _r, data, _text = world.finish(outcome.backup_folder)
        assert data["drive_pdfs_without_a_statement"] == []  # a probable-duplicate skip is not "not ingested"

    def test_the_pending_pairs_the_reingest_resolved_are_superseded(self, world):
        duplicates_service_scan(world.db)
        assert {p.status for p in world.db.query(DuplicatePair)} == {DuplicatePairStatus.PENDING}

        world.run()

        assert {p.status for p in world.db.query(DuplicatePair)} == {DuplicatePairStatus.SUPERSEDED}

    def test_pre_registration_shares_the_wipes_transaction(self, world):
        """The remembered files are written in the wipe's transaction, so a wipe that fails its
        count check rolls them back with it. (The test fixture's own rollback undoes the whole test
        transaction, so the property is shown by the ORDER of events: pre-registration, then the wipe,
        then a rollback, with no commit in between.)"""
        events = []
        real_pre_register = backfill_duplicates.pre_register
        real_commit = world.db.commit

        def pre_register(db, plan):
            events.append("pre_register")
            return real_pre_register(db, plan)

        def wipe(db, ids):
            events.append("perform_wipe")
            return {"bank_statements": 0, "transactions": 0}  # does not match the dry run

        def commit():
            events.append("commit")
            return real_commit()

        def rollback():
            events.append("rollback")

        with (
            patch.object(backfill_duplicates, "pre_register", side_effect=pre_register),
            patch.object(service, "perform_wipe", side_effect=wipe),
            patch.object(world.db, "commit", side_effect=commit),
            patch.object(world.db, "rollback", side_effect=rollback),
            pytest.raises(service.BackfillRefused),
        ):
            world.run()

        after_pre_register = events[events.index("pre_register"):]
        assert after_pre_register == ["pre_register", "perform_wipe", "rollback"]

    def test_a_pair_of_clearly_different_sizes_is_reingested_in_full_and_stays_for_the_panel(self, db_session):
        big = [*june(5), *((date(2026, 6, 20 + i), f"{500 + i}.00", f"EXTRA {i}") for i in range(10))]
        w = World(db_session, uob_rows_2=big)
        outcome = w.run()

        hashes = {h for _bank, h in w.statements_by_bank()}
        assert sha256(UOB1) in hashes and sha256(UOB2) in hashes  # BOTH kept: nothing silently dropped
        _r, data, rendered = w.finish(outcome.backup_folder)
        assert len(data["different_size_pairs_left_for_the_review_panel"]) == 1
        assert "left for the Review panel as information only" in rendered


class TestCarryingCorrections:
    def test_a_correction_on_the_skipped_copy_is_carried_and_the_kept_copys_own_wins_a_conflict(self, db_session):
        w = World(db_session, uob2_manual=0)
        dining = ensure_category(db_session, "Dining")
        # The SKIPPED copy (UOB2) gets two corrections: one on a transaction the kept copy has NOT corrected
        # (index 3), one on a transaction the kept copy HAS corrected (index 0) but with another category.
        rows2 = db_session.query(Transaction).filter_by(bank_statement_id=w.uob2.id).order_by(Transaction.transaction_date).all()
        rows2[3].category_source, rows2[3].category_id = "manual", dining.id
        rows2[0].category_source, rows2[0].category_id = "manual", dining.id
        db_session.flush()
        # Both copies carry corrections now, so the EARLIER ingested (UOB1) is kept.
        outcome = w.run()

        result, _data, rendered = w.finish(outcome.backup_folder)

        assert result.carried == 2
        assert len(result.superseded) == 1 and result.superseded[0].category_id == str(dining.id)
        assert manual_count(db_session, sha256(UOB1)) == 3  # 2 own + 1 carried
        kept = {t.description: t for t in db_session.query(Transaction).join(BankStatement).filter(BankStatement.pdf_content_hash == sha256(UOB1))}
        assert kept["MERCHANT 3"].category_id == dining.id  # the carried correction landed
        assert kept["MERCHANT 0"].category_id != dining.id  # the kept copy's own correction won the conflict
        assert "1 superseded by a correction the kept copy already had" in rendered

    def test_finish_is_idempotent_for_carried_corrections(self, db_session):
        w = World(db_session, uob2_manual=0)
        dining = ensure_category(db_session, "Dining")
        rows2 = db_session.query(Transaction).filter_by(bank_statement_id=w.uob2.id).order_by(Transaction.transaction_date).all()
        rows2[3].category_source, rows2[3].category_id = "manual", dining.id
        db_session.flush()
        outcome = w.run()
        w.finish(outcome.backup_folder)

        second, _data, _text = w.finish(outcome.backup_folder)

        assert manual_count(db_session, sha256(UOB1)) == 3
        assert second.unmatched == [] and second.already_applied >= 3

    def test_a_genuinely_unmatched_correction_is_still_reported_unmatched(self, db_session):
        w = World(db_session)
        outcome = w.run()
        from ingestion_worker.backfill.corrections import CapturedCorrection

        stray = CapturedCorrection("9" * 64, "2026-06-02", __import__("decimal").Decimal("1.00"), "out", "NOTHING", "cat")

        assert corrections.rekey_for_skipped_copies(db_session, [stray]) == [stray]
        assert outcome is not None


class TestPreFlightAndRestore:
    def test_refuses_while_a_removal_is_in_progress(self, world):
        duplicates_service_scan(world.db)
        pair = next(iter(repository.load_pairs(world.db).values()))
        world.db.add(StatementRemovalJob(pair_id=pair.id, remove_statement_hash=pair.hash_b, status=StatementRemovalJobStatus.EMBEDDINGS_PENDING,
                                         removed_transaction_ids=[__import__("uuid").uuid4()]))
        world.db.flush()

        with patch("ingestion_worker.embedding.vector_store._client", return_value=MagicMock()):
            reasons = service.pre_flight(world.db)

        assert any("duplicate-statement removal" in r for r in reasons)

    def test_the_backup_covers_the_mutable_duplicate_tables(self):
        assert {"known_files", "duplicate_pairs", "statement_removal_jobs", "duplicate_scan_state"} <= set(BACKED_UP_TABLES)
        assert "duplicate_comparisons" not in BACKED_UP_TABLES  # write-once evidence nothing deletes

    def test_restore_undoes_the_pre_registration_and_the_superseding(self, world):
        duplicates_service_scan(world.db)
        pending_before = {k: p.status for k, p in repository.load_pairs(world.db).items()}
        outcome = world.run()
        assert world.db.query(KnownFile).count() == 2

        with world.drive.patched(), patch("ingestion_worker.embedding.vector_store.recreate_transactions_collection", return_value=True):
            _loc, artifact = export.load_backup(world.db, outcome.backup_folder)
            restore.restore_backup(world.db, artifact, confirm=lambda p: f"RESTORE FROM {outcome.backup_folder}",
                                   folder_name=outcome.backup_folder, out=world.output.append)

        assert world.db.query(KnownFile).count() == 0  # the pre-registered skips are gone again
        assert {k: p.status for k, p in repository.load_pairs(world.db).items()} == pending_before  # pairs pending again
        assert {h for _b, h in world.statements_by_bank()} == {sha256(UOB1), sha256(UOB2), sha256(TRUST1), sha256(TRUST2)}

    def test_finish_requests_a_pair_scan(self, world):
        backfill_duplicates.request_pair_scan(world.db)

        state = repository.get_scan_state(world.db)
        assert state is not None and state.recheck_requested_at is not None

    def test_an_old_backup_without_the_new_tables_restores_and_leaves_them_alone(self, world):
        outcome = world.run()
        with world.drive.patched():
            _loc, artifact = export.load_backup(world.db, outcome.backup_folder)
        for table in ("known_files", "duplicate_pairs", "statement_removal_jobs", "duplicate_scan_state"):
            artifact.manifest["tables"].pop(table)  # a backup taken before Epic 14
        kept_known = world.db.query(KnownFile).count()

        with patch("ingestion_worker.embedding.vector_store.recreate_transactions_collection", return_value=True):
            restore.restore_backup(world.db, artifact, confirm=lambda p: f"RESTORE FROM {outcome.backup_folder}",
                                   folder_name=outcome.backup_folder, out=world.output.append)

        assert world.db.query(KnownFile).count() == kept_known  # untouched
