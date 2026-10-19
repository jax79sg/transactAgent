"""The Backfill Tool's `run`, `finish`, and `restore` flows (WR-52..WR-56), end to end against
a real PostgreSQL with an in-memory fake Drive; extraction, classification, and the vector
store are mocked at their module boundaries. Nothing here touches any real data."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from backfill_helpers import FEB_RESPONSE, JAN_RESPONSE, FakeDrive, seed_legacy
from sqlalchemy import text
from transactagent_db.models import (
    Account,
    BankStatement,
    IngestionRun,
    IngestionRunStatus,
    RecategorizationJob,
    StatementAccount,
    Transaction,
)

from ingestion_worker.backfill import corrections, export, report, restore, service
from ingestion_worker.backfill.tables import BACKED_UP_TABLES


class Harness:
    def __init__(self, db_session):
        self.db = db_session
        self.drive = FakeDrive()
        self.seed = seed_legacy(db_session, self.drive)
        # Plain ids captured up front: the wipe deletes rows, and touching an expired ORM
        # object whose row is gone raises ObjectDeletedError.
        self.ids = SimpleNamespace(
            s1=self.seed.s1.id, s2=self.seed.s2.id, s3=self.seed.s3.id, run_file=self.seed.run_file.id,
            user=self.seed.user.id, ntuc=self.seed.ntuc.id,
        )
        self.vector_recreated = 0
        self.vector_ok = True
        self.output: list[str] = []

    def run(self, *, confirm="WIPE 2 STATEMENTS", responses=(JAN_RESPONSE, FEB_RESPONSE)):
        def recreate():
            self.vector_recreated += 1
            return self.vector_ok

        with (
            self.drive.patched(),
            patch("ingestion_worker.embedding.vector_store._client", return_value=MagicMock()),
            patch("ingestion_worker.embedding.vector_store.recreate_transactions_collection", side_effect=recreate),
            patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"page"]),
            patch("ingestion_worker.extraction.service.extract_statement_raw", side_effect=list(responses)),
            patch(
                "ingestion_worker.orchestrator.pipeline.classify_batch",
                side_effect=lambda db, items: {d: "Groceries" for d, _ in items},
            ),
        ):
            return service.run_backfill(
                self.db,
                snapshot=lambda: nullcontext(self.db.connection()),
                confirm=lambda prompt: confirm,
                out=self.output.append,
                sleep=lambda s: None,
            )

    def counts(self):
        return {t: self.db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in BACKED_UP_TABLES}


@pytest.fixture
def h(db_session):
    return Harness(db_session)


class TestWipeSet:
    def test_unconverted_statements_with_a_pdf_in_drive_are_wiped_the_rest_are_not(self, h):
        wipe = service.compute_wipe_set(h.db, {"pdf-1", "pdf-2"})

        assert sorted(wipe.statement_ids) == sorted([str(h.ids.s1), str(h.ids.s2)])
        assert [k["drive_file_id"] for k in wipe.kept_missing_pdf] == ["pdf-gone"]
        assert wipe.already_converted == 0

    def test_a_statement_that_already_has_sections_is_never_wiped(self, h):
        account = Account(name="A", bank_name="Trust Bank", currency="SGD")
        h.db.add(account)
        h.db.flush()
        h.db.add(StatementAccount(bank_statement_id=h.ids.s2, account_id=account.id))
        h.db.flush()

        wipe = service.compute_wipe_set(h.db, {"pdf-1", "pdf-2"})

        assert wipe.statement_ids == [str(h.ids.s1)] and wipe.already_converted == 1


class TestPreFlight:
    def _flight(self, h, *, vector_ok=True):
        client = MagicMock()
        if not vector_ok:
            client.get_collections.side_effect = ConnectionError("refused")
        with patch("ingestion_worker.embedding.vector_store._client", return_value=client):
            return service.pre_flight(h.db)

    def test_clear_when_nothing_is_running(self, h):
        assert self._flight(h) == []

    def test_refuses_while_an_ingestion_run_is_active(self, h):
        h.db.add(IngestionRun(triggered_by_user_id=h.ids.user, status=IngestionRunStatus.RUNNING))
        h.db.flush()

        assert any("ingestion run" in r for r in self._flight(h))

    def test_refuses_while_a_recategorization_job_is_active(self, h):
        h.db.add(RecategorizationJob(source_transaction_id=h.ids.ntuc, status="queued"))
        h.db.flush()

        assert any("recategorization job" in r for r in self._flight(h))

    def test_refuses_when_the_vector_store_is_unreachable(self, h):
        assert any("vector store" in r for r in self._flight(h, vector_ok=False))

    def test_refuses_without_a_user_to_attribute_the_run_to(self, h):
        h.db.execute(text("DELETE FROM ingestion_run_files"))
        h.db.execute(text("DELETE FROM ingestion_runs"))
        h.db.execute(text("DELETE FROM users"))

        assert any("no user" in r for r in self._flight(h))


class TestDryRun:
    def test_counts_what_would_go_and_changes_nothing(self, h):
        before = h.counts()
        report_ = service.dry_run(h.db, h.drive.list_folder_pdf_files(None))

        assert report_.counts == {
            "statements": 2, "transactions": 5, "manual_corrections": 3, "recategorization_jobs": 1,
            "recategorization_proposals": 2, "categorization_disagreements": 1, "recurring_payment_matches": 1,
        }
        assert h.counts() == before
        rendered = service.render_dry_run(report_)
        assert "KEPT because their PDF is missing from Drive: 1" in rendered and "DRY RUN" in rendered


class TestWipe:
    def test_the_wipe_is_scoped_to_the_wipe_set_and_leaves_everything_else(self, h):
        ids = [str(h.ids.s1), str(h.ids.s2)]

        deleted = service.perform_wipe(h.db, ids)

        assert (deleted["bank_statements"], deleted["transactions"]) == (2, 5)
        assert deleted["recategorization_proposals"] == 2 and deleted["recategorization_jobs"] == 1
        # the kept statement and everything depending on it survive
        assert [s.drive_file_id for s in h.db.query(BankStatement).all()] == ["pdf-gone"]
        assert [t.description for t in h.db.query(Transaction).all()] == ["GONE"]
        assert h.db.execute(text("SELECT count(*) FROM recategorization_jobs")).scalar_one() == 1  # gone_job
        assert h.db.execute(text("SELECT count(*) FROM categorization_disagreements")).scalar_one() == 1
        assert h.db.execute(text("SELECT count(*) FROM recurring_payment_matches")).scalar_one() == 1
        # the run-file link was detached, not deleted
        link = h.db.execute(
            text("SELECT bank_statement_id FROM ingestion_run_files WHERE id = :i"), {"i": h.ids.run_file}
        ).scalar_one()
        assert link is None
        # accounts, categories, users are never touched
        assert h.db.execute(text("SELECT count(*) FROM categories")).scalar_one() == 3

    def test_remaining_transactions_are_requeued_for_embedding(self, h):
        h.db.execute(text("UPDATE transactions SET embedding_status = 'completed'"))

        assert service.reset_remaining_embeddings(h.db) == 6
        assert h.db.execute(text("SELECT count(*) FROM transactions WHERE embedding_status <> 'pending'")).scalar_one() == 0


class TestRun:
    def test_end_to_end_backup_wipe_reingest_and_finish(self, h):
        outcome = h.run()

        # 1. a verified backup exists in a timestamped subfolder
        assert outcome.backup_folder and outcome.backup_folder.startswith("pre-backfill-")
        assert set(h.drive.files_in(outcome.backup_folder)) == {f"{t}.jsonl" for t in BACKED_UP_TABLES} | {"manifest.json"}
        assert any("Backup verified" in line for line in h.output)
        # 2. the wipe and reingest happened; the vector collection was recreated once
        assert h.vector_recreated == 1
        statements = {s.drive_file_id: s for s in h.db.query(BankStatement).all()}
        assert set(statements) == {"pdf-1", "pdf-2", "pdf-gone"}
        assert statements["pdf-gone"].id == h.ids.s3  # the kept one is the ORIGINAL row
        assert statements["pdf-1"].id != h.ids.s1  # re-created
        # 3. every re-ingested statement has sections; FEB has two (a savings account and a credit card)
        sections = {k: h.db.query(StatementAccount).filter_by(bank_statement_id=s.id).count() for k, s in statements.items()}
        assert sections == {"pdf-1": 1, "pdf-2": 2, "pdf-gone": 0}
        assert {a.name for a in h.db.query(Account).all()} == {"OCBC Bank 3456", "Trust Bank 9988", "Trust Bank 4111"}
        closing = h.db.query(StatementAccount).filter(StatementAccount.closing_balance.isnot(None)).one()
        assert str(closing.closing_balance) == "900.00"
        # 4. every transaction of a re-ingested statement is linked to a section of its own statement
        orphans = h.db.execute(text("SELECT count(*) FROM transactions t JOIN bank_statements bs ON bs.id = t.bank_statement_id WHERE bs.drive_file_id <> 'pdf-gone' AND t.statement_account_id IS NULL")).scalar_one()
        assert orphans == 0
        # 5. the reingest was an ordinary run, left in a terminal state
        run = h.db.get(IngestionRun, outcome.reingest_run_id)
        assert run.status == IngestionRunStatus.COMPLETED and run.files_processed_count == 2
        # 6. the manual corrections are NOT back yet (that is `finish`)...
        assert h.db.query(Transaction).filter_by(category_source="manual").count() == 1  # only the kept 'GONE'

        # ...finish re-applies them from the backup artifact and writes the report
        with h.drive.patched():
            location, artifact = export.load_backup(h.db, outcome.backup_folder)
            result = corrections.apply_corrections(h.db, corrections.capture_corrections(artifact))
            data = report.build_report(h.db, artifact, result, h.drive.list_folder_pdf_files(None))
            rendered = report.render_report(data)
            report.save_report(h.db, location, data, rendered)

        assert (result.captured, result.applied, result.unmatched) == (3, 3, [])
        assert h.db.query(Transaction).filter_by(category_source="manual").count() == 4  # 3 re-applied + GONE
        assert data["statements_wiped"] == 2 and data["statements_reingested"] == 2
        assert [k["drive_file_id"] for k in data["statements_kept_missing_pdf"]] == ["pdf-gone"]
        assert [m["bank"] for m in data["multi_account_statements"]] == ["Trust Bank"]
        assert data["recurring_payment_matches_discarded"] == 1
        assert "completion-report.json" in h.drive.files_in(outcome.backup_folder)
        assert "Statements with more than one account section: 1" in rendered

    def test_nothing_is_wiped_when_the_typed_confirmation_is_wrong(self, h):
        before = h.counts()

        with pytest.raises(service.BackfillRefused, match="confirmation did not match"):
            h.run(confirm="yes please")

        assert h.counts() == before and h.vector_recreated == 0

    def test_nothing_is_wiped_when_the_backup_cannot_be_verified(self, h):
        h.drive.corrupt_downloads_of = {"transactions.jsonl"}
        before = h.counts()

        with pytest.raises(service.BackfillRefused, match="could not be verified"):
            h.run()

        assert h.counts() == before and h.vector_recreated == 0

    def test_a_vector_store_failure_stops_before_the_reingest(self, h):
        h.vector_ok = False

        with pytest.raises(service.BackfillRefused, match="vector store collection could not be recreated"):
            h.run()

        assert h.vector_recreated == 3  # retried
        assert h.db.query(IngestionRun).filter_by(status=IngestionRunStatus.RUNNING).count() == 0  # no reingest run started

    def test_refuses_to_start_while_a_run_is_active(self, h):
        h.db.add(IngestionRun(triggered_by_user_id=h.ids.user, status=IngestionRunStatus.RUNNING))
        h.db.flush()
        before = h.counts()

        with pytest.raises(service.BackfillRefused, match="refusing to start"):
            h.run()

        assert h.counts() == before

    def test_running_again_after_conversion_wipes_nothing_and_takes_no_new_backup(self, h):
        h.run()
        folders_after_first = h.drive.folder_names()
        statements_after_first = {s.id for s in h.db.query(BankStatement).all()}

        # the second run: every PDF-backed statement now has sections, so there is nothing to wipe
        second = h.run(responses=())  # the reingest skips both PDFs as duplicates, so no extraction calls

        assert second.nothing_to_wipe and second.backup_folder is None
        assert h.drive.folder_names() == folders_after_first
        assert {s.id for s in h.db.query(BankStatement).all()} == statements_after_first


class TestInterruptedRunIsResumable:
    def test_a_failed_reingest_is_finished_by_running_again_and_finish_still_has_the_corrections(self, h):
        # First attempt: the second PDF cannot be read, so its statement is not re-created.
        first = h.run(responses=(JAN_RESPONSE, "not valid json"))
        statements = {s.drive_file_id for s in h.db.query(BankStatement).all()}
        assert statements == {"pdf-1", "pdf-gone"}  # pdf-2 was wiped and not yet re-ingested
        assert h.db.get(IngestionRun, first.reingest_run_id).status == IngestionRunStatus.COMPLETED_WITH_FAILURES
        folders_after_first = h.drive.folder_names()

        # Running again: nothing is left to wipe (pdf-1 is already converted, pdf-gone has no PDF),
        # so it goes straight to the reingest and re-reads only what is still missing.
        second = h.run(responses=(FEB_RESPONSE,))

        assert second.nothing_to_wipe and second.backup_folder is None
        assert h.drive.folder_names() == folders_after_first  # no second backup
        assert {s.drive_file_id for s in h.db.query(BankStatement).all()} == {"pdf-1", "pdf-2", "pdf-gone"}
        assert h.db.query(StatementAccount).count() == 3

        # `finish` against the ORIGINAL backup still re-applies all three manual corrections.
        with h.drive.patched():
            _, artifact = export.load_backup(h.db, first.backup_folder)
            result = corrections.apply_corrections(h.db, corrections.capture_corrections(artifact))

        assert (result.captured, result.applied, result.unmatched) == (3, 3, [])


class TestIdenticalCopiesInDrive:
    def test_a_byte_identical_copy_is_skipped_and_reported_as_such_not_as_missing(self, h):
        """Duplicate detection is by the PDF's bytes, so a second Drive file with the same bytes
        is recognized and skipped. The report must say so, not claim it is 'not ingested yet'."""
        h.drive.add_pdf("pdf-2-copy", "feb-trust-copy.pdf", b"PDF-TWO")  # same bytes as pdf-2
        outcome = h.run(confirm="WIPE 2 STATEMENTS")

        statements = h.db.query(BankStatement).all()
        assert sorted(s.drive_file_id for s in statements) == ["pdf-1", "pdf-2", "pdf-gone"]  # still ONE statement for those bytes
        with h.drive.patched():
            _, artifact = export.load_backup(h.db, outcome.backup_folder)
            data = report.build_report(
                h.db, artifact, corrections.CorrectionResult(), h.drive.list_folder_pdf_files(None)
            )

        assert data["identical_copies_skipped_as_duplicates"] == ["feb-trust-copy.pdf"]
        assert data["drive_pdfs_without_a_statement"] == []
        assert "Byte-identical copies skipped as duplicates (1): feb-trust-copy.pdf" in report.render_report(data)


class TestRestore:
    def _snapshot(self, db):
        return {
            t: db.execute(text(f'SELECT to_jsonb(x) - \'embedding_status\' FROM "{t}" x ORDER BY x.id')).scalars().all()
            for t in ("bank_statements", "transactions", "recategorization_jobs", "recategorization_proposals",
                      "categorization_disagreements", "recurring_payment_matches")
        }

    def test_restore_puts_every_backed_up_table_back_exactly(self, h):
        before = self._snapshot(h.db)
        run_links_before = h.db.execute(text("SELECT id::text, bank_statement_id::text FROM ingestion_run_files ORDER BY id")).all()
        outcome = h.run()
        assert self._snapshot(h.db) != before  # the backfill really changed things

        with h.drive.patched(), patch("ingestion_worker.embedding.vector_store.recreate_transactions_collection", return_value=True) as recreate:
            _, artifact = export.load_backup(h.db, outcome.backup_folder)
            restore.restore_backup(h.db, artifact, confirm=lambda p: f"RESTORE FROM {outcome.backup_folder}", folder_name=outcome.backup_folder, out=lambda m: None)

        assert self._snapshot(h.db) == before
        assert h.db.execute(text("SELECT id::text, bank_statement_id::text FROM ingestion_run_files WHERE id = :i"), {"i": h.ids.run_file}).all() == [
            r for r in run_links_before if r[0] == str(h.ids.run_file)
        ]
        assert h.db.execute(text("SELECT count(*) FROM transactions WHERE embedding_status <> 'pending'")).scalar_one() == 0
        recreate.assert_called_once()

    def test_a_wrong_confirmation_changes_nothing(self, h):
        outcome = h.run()
        before = self._snapshot(h.db)

        with h.drive.patched():
            _, artifact = export.load_backup(h.db, outcome.backup_folder)
            with pytest.raises(service.BackfillRefused, match="confirmation did not match"):
                restore.restore_backup(h.db, artifact, confirm=lambda p: "nope", folder_name=outcome.backup_folder, out=lambda m: None)

        assert self._snapshot(h.db) == before
