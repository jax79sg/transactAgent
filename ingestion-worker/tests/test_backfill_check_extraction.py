"""`check-extraction` (NFR-AB-3): compare the NEW extraction with what the database already
holds on real PDFs, read-only. Extraction is mocked at the Gemini boundary; the comparison
logic, the sampling, and the read-only guarantee are real."""

from unittest.mock import patch

import pytest
from backfill_helpers import FEB_RESPONSE, JAN_RESPONSE, FakeDrive, seed_legacy
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ingestion_worker.backfill import check_extraction as check
from ingestion_worker.backfill.__main__ import _interactive_confirm, build_parser, main
from ingestion_worker.backfill.service import BackfillRefused


def _run(db, drive, responses, *, limit=None):
    out: list[str] = []
    with (
        drive.patched(),
        patch("ingestion_worker.extraction.service._pdf_to_page_images", return_value=[b"page"]),
        patch("ingestion_worker.extraction.service.extract_statement_raw", side_effect=list(responses)),
    ):
        results = check.check_extraction(db, limit=limit, drive_files=drive.list_folder_pdf_files(None), out=out.append)
    return results, out


class TestCheckExtraction:
    def test_reports_matches_mismatches_multi_account_pdfs_and_missing_pdfs(self, db_session):
        drive = FakeDrive()
        seed_legacy(db_session, drive)

        # statements are visited round-robin by bank name: HSBC (pdf-gone), OCBC Bank (pdf-1), Trust Bank (pdf-2)
        results, out = _run(db_session, drive, [JAN_RESPONSE, FEB_RESPONSE])

        by_file = {r.drive_file_id: r for r in results}
        assert by_file["pdf-gone"].status == "pdf_missing_from_drive"
        jan, feb = by_file["pdf-1"], by_file["pdf-2"]
        assert (jan.status, jan.sections, jan.stored_count, jan.new_count, jan.only_stored, jan.only_new) == ("ok", 1, 4, 4, 0, 0)
        assert (feb.status, feb.sections, feb.only_new, feb.only_stored) == ("mismatch", 2, 1, 0)  # AMAZON is new
        assert feb.account_tails == ["9988", "4111"]
        summary = check.render_summary(results)
        assert "Multi-account PDFs among them: 1" in summary and "Trust Bank" in summary
        assert any("MULTI-ACCOUNT" in line for line in out)

    def test_an_extraction_failure_is_reported_not_raised(self, db_session):
        drive = FakeDrive()
        seed_legacy(db_session, drive)

        results, _ = _run(db_session, drive, ["not json", "not json"])

        assert {r.status for r in results if r.drive_file_id in ("pdf-1", "pdf-2")} == {"extraction_failed"}

    def test_writes_nothing_to_the_database(self, db_session):
        drive = FakeDrive()
        seed_legacy(db_session, drive)
        before = {t: db_session.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one()
                  for t in ("bank_statements", "transactions", "accounts", "statement_accounts", "ingestion_runs")}

        _run(db_session, drive, [JAN_RESPONSE, FEB_RESPONSE])

        after = {t: db_session.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in before}
        assert after == before

    def test_the_session_really_is_read_only(self, db_session):
        drive = FakeDrive()
        seed_legacy(db_session, drive)

        def attempt_a_write(*_args, **_kwargs):
            db_session.execute(text("INSERT INTO accounts (id, name, bank_name, currency) VALUES (gen_random_uuid(), 'x', 'y', 'SGD')"))

        with patch.object(check, "_stored_transactions", side_effect=attempt_a_write), pytest.raises(DBAPIError, match="read-only"):
            _run(db_session, drive, [JAN_RESPONSE, FEB_RESPONSE])

    def test_a_small_sample_still_spans_every_bank(self, db_session):
        seed_legacy(db_session, FakeDrive())

        chosen = check.choose_statements(db_session, limit=2)

        assert len({row.bank_name for row in chosen}) == 2

    def test_limit_none_means_every_statement(self, db_session):
        seed_legacy(db_session, FakeDrive())

        assert len(check.choose_statements(db_session, limit=None)) == 3


class TestCommandLine:
    def test_parser_accepts_every_command(self):
        parser = build_parser()
        assert parser.parse_args(["run"]).command == "run"
        assert parser.parse_args(["finish", "--backup", "pre-backfill-X"]).backup == "pre-backfill-X"
        assert parser.parse_args(["restore", "--backup", "pre-backfill-X"]).command == "restore"
        assert parser.parse_args(["check-extraction", "--limit", "3"]).limit == 3
        assert parser.parse_args(["check-extraction", "--all"]).all is True

    def test_finish_and_restore_require_a_backup_name(self):
        for command in ("finish", "restore"):
            with pytest.raises(SystemExit):
                build_parser().parse_args([command])

    def test_a_typed_confirmation_is_refused_outside_an_interactive_terminal(self):
        with pytest.raises(BackfillRefused, match="interactive terminal"):
            _interactive_confirm("type it: ")  # pytest's stdin is not a TTY

    def test_a_refusal_exits_with_code_2_and_a_message(self, capsys):
        with (
            patch("ingestion_worker.backfill.__main__.run_migrations_with_lock"),
            # main() builds its command table at call time, so patching the module attribute takes effect
            patch("ingestion_worker.backfill.__main__.cmd_run", side_effect=BackfillRefused("nothing was changed")),
        ):
            code = main(["run"])

        assert code == 2
        assert "REFUSED: nothing was changed" in capsys.readouterr().err
