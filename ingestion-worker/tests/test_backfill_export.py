"""The backfill's backup (WR-54): export, upload, verification by download, and loading."""

import json
from decimal import Decimal

import pytest
from backfill_helpers import FakeDrive, seed_legacy
from sqlalchemy import text

from ingestion_worker.backfill import export
from ingestion_worker.backfill.tables import BACKED_UP_TABLES, MANIFEST_FILE
from ingestion_worker.config import settings


def _built(db_session, drive):
    seed = seed_legacy(db_session, drive)
    artifact = export.build_backup(db_session.connection(), extra_manifest={"wipe_set_statement_ids": [str(seed.s1.id)]})
    return seed, artifact


class TestBuildBackup:
    def test_one_file_per_table_plus_a_manifest_with_counts_and_checksums(self, db_session):
        _, artifact = _built(db_session, FakeDrive())

        assert set(artifact.files) == {f"{t}.jsonl" for t in BACKED_UP_TABLES} | {MANIFEST_FILE}
        tables = artifact.manifest["tables"]
        assert tables["bank_statements"]["row_count"] == 3
        assert tables["transactions"]["row_count"] == 6
        assert tables["statement_accounts"]["row_count"] == 0
        for name, info in tables.items():
            assert info["sha256"] == export._sha256(artifact.files[f"{name}.jsonl"])
            assert artifact.files[f"{name}.jsonl"].count(b"\n") == info["row_count"]
        assert artifact.manifest["wipe_set_statement_ids"]

    def test_rows_round_trip_exactly_including_numerics_and_enums(self, db_session):
        seed, artifact = _built(db_session, FakeDrive())

        rows = {r["description"]: r for r in export.read_rows(artifact, "transactions") if r["description"] == "NTUC"}
        row = rows["NTUC"]
        assert row["out_flow"] == Decimal("25.50") and isinstance(row["out_flow"], Decimal)
        assert row["category_source"] == "manual" and row["in_flow"] is None
        assert row["id"] == str(seed.ntuc.id)

    def test_an_empty_table_exports_an_empty_file(self, db_session):
        _, artifact = _built(db_session, FakeDrive())

        assert artifact.files["statement_accounts.jsonl"] == b""
        assert export.read_rows(artifact, "statement_accounts") == []

    def test_folder_names_are_timestamped_and_prefixed(self):
        from datetime import UTC, datetime

        assert export.backup_folder_name(datetime(2026, 10, 3, 8, 15, 0, tzinfo=UTC)) == "pre-backfill-20261003T081500Z"


class TestSnapshotConnection:
    def test_a_repeatable_read_connection_exports_every_table_consistently(self, engine):
        """The CLI reads the backup through a REPEATABLE READ connection (one snapshot for all
        tables). This exercises that exact connection setup against a real database."""
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            artifact = export.build_backup(conn, extra_manifest={"wipe_set_statement_ids": []})
            isolation = conn.execute(text("SHOW transaction_isolation")).scalar_one()
            live = {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in BACKED_UP_TABLES}

        assert isolation == "repeatable read"
        assert {t: info["row_count"] for t, info in artifact.manifest["tables"].items()} == live


class TestUploadAndVerify:
    def test_a_clean_upload_verifies(self, db_session):
        drive = FakeDrive()
        _, artifact = _built(db_session, drive)

        with drive.patched():
            location = export.upload_backup(db_session, artifact, "pre-backfill-T1")
            problems = export.verify_uploaded_backup(db_session, location, artifact)

        assert problems == []
        assert set(drive.files_in("pre-backfill-T1")) == set(artifact.files)

    def test_a_damaged_download_is_reported(self, db_session):
        drive = FakeDrive()
        _, artifact = _built(db_session, drive)
        drive.corrupt_downloads_of = {"transactions.jsonl"}

        with drive.patched():
            location = export.upload_backup(db_session, artifact, "pre-backfill-T1")
            problems = export.verify_uploaded_backup(db_session, location, artifact)

        assert any("transactions.jsonl" in p and "does not match" in p for p in problems)

    def test_a_missing_file_is_reported(self, db_session):
        drive = FakeDrive()
        _, artifact = _built(db_session, drive)

        with drive.patched():
            location = export.upload_backup(db_session, artifact, "pre-backfill-T1")
            victim = next(i for i, n in drive.nodes.items() if n["name"] == "bank_statements.jsonl")
            del drive.nodes[victim]
            problems = export.verify_uploaded_backup(db_session, location, artifact)

        assert any("bank_statements.jsonl" in p and "not found" in p for p in problems)


class TestLoadBackup:
    def test_loads_and_checks_every_file_against_the_manifest(self, db_session):
        drive = FakeDrive()
        _, artifact = _built(db_session, drive)
        with drive.patched():
            export.upload_backup(db_session, artifact, "pre-backfill-T1")
            location, loaded = export.load_backup(db_session, "pre-backfill-T1")

        assert location.folder_name == "pre-backfill-T1"
        assert loaded.manifest == json.loads(artifact.files[MANIFEST_FILE])
        assert export.read_rows(loaded, "transactions") == export.read_rows(artifact, "transactions")

    def test_a_tampered_file_is_refused(self, db_session):
        drive = FakeDrive()
        _, artifact = _built(db_session, drive)
        with drive.patched():
            export.upload_backup(db_session, artifact, "pre-backfill-T1")
            node = next(n for n in drive.nodes.values() if n["name"] == "transactions.jsonl")
            node["content"] = node["content"] + b'{"tampered": true}\n'
            with pytest.raises(export.BackupError, match="does not match its checksum"):
                export.load_backup(db_session, "pre-backfill-T1")

    def test_an_unknown_folder_is_refused(self, db_session):
        drive = FakeDrive()
        with drive.patched(), pytest.raises(export.BackupError, match="No backup folder named"):
            export.load_backup(db_session, "pre-backfill-NOPE")

    def test_a_folder_without_a_manifest_is_refused(self, db_session):
        drive = FakeDrive()
        with drive.patched():
            root = drive.ensure_backup_folder_exists(db_session, settings.google_drive_backup_folder_id)
            drive.ensure_subfolder(db_session, root, "pre-backfill-EMPTY")
            with pytest.raises(export.BackupError, match=r"manifest\.json"):
                export.load_backup(db_session, "pre-backfill-EMPTY")
