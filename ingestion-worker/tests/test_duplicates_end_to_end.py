"""The whole feature once, through the real pipeline, scan and handler (real PostgreSQL, fake
Drive, mocked extraction and vector store): two downloads of the same statement are ingested the way
they are TODAY (detection off), detection is switched on, the scan finds the pair, the user confirms the
removal, the handler removes the duplicate and its embeddings, and a later ingestion run recognises the
removed copy's file without reading it again."""

import hashlib
from unittest.mock import patch

from duplicates_helpers import extracted, june
from sqlalchemy import select
from transactagent_db.models import (
    BankStatement,
    Category,
    DuplicatePair,
    DuplicatePairStatus,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
    User,
)

from ingestion_worker import config
from ingestion_worker.clients.drive_client import DriveFileRef
from ingestion_worker.duplicates import removal, repository, service
from ingestion_worker.orchestrator import pipeline

FIRST, SECOND = b"JUN-2026-DOWNLOAD-JULY", b"JUN-2026-DOWNLOAD-AUGUST"


def _run(db, extract):
    user = db.query(User).first() or User(username="owner", password_hash="x")
    db.add(user)
    db.flush()
    run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
    db.add(run)
    db.flush()
    refs = [DriveFileRef(id="id-1", name="JUN 2026_0728.pdf"), DriveFileRef(id="id-2", name="JUN 2026_0828.pdf")]
    contents = {"id-1": FIRST, "id-2": SECOND}
    with (
        patch("ingestion_worker.clients.drive_client.list_folder_pdf_files", return_value=refs),
        patch("ingestion_worker.clients.drive_client.download_file", side_effect=lambda _d, ref: contents[ref.id]),
        patch("ingestion_worker.orchestrator.pipeline.extract_statement", side_effect=extract) as extract_mock,
        patch("ingestion_worker.orchestrator.pipeline.classify_batch", return_value={}),
    ):
        pipeline.process_run(db, run)
    db.refresh(run)
    return run, extract_mock


def test_two_downloads_of_one_statement_from_ingestion_to_removal_to_a_quiet_next_run(db_session, monkeypatch):
    for name in ("Groceries", "UNSURE"):
        db_session.add(Category(name=name, active=True, is_reserved=(name == "UNSURE")))
    db_session.flush()
    statement = extracted(june(5), bank="UOB")

    # 1. Today's behaviour (detection ships OFF): both downloads are ingested, so the statement is counted twice.
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
    run1, _ = _run(db_session, lambda _pdf: statement)
    assert run1.files_processed_count == 2 and db_session.query(BankStatement).count() == 2
    assert db_session.query(Transaction).count() == 10

    # 2. Detection is switched on (after the accuracy check); the scan finds the pair.
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)
    assert service.is_pair_scan_due_now(db_session) is True
    service.run_pair_scan(db_session)
    (pair,) = db_session.query(DuplicatePair).all()
    assert pair.status is DuplicatePairStatus.PENDING and pair.removal_allowed is True
    assert service.is_pair_scan_due_now(db_session) is False
    kept_hash = pair.keep_hash
    removed_hash = pair.hash_a if pair.hash_b == kept_hash else pair.hash_b

    # 3. The user confirms the removal in the app (what the API writes), and the worker's removal branch runs.
    db_session.add(StatementRemovalJob(pair_id=pair.id, remove_statement_hash=removed_hash, corrections_acknowledged=0))
    db_session.flush()
    removed_ids = sorted(
        str(t.id)
        for t in db_session.scalars(select(Transaction).join(BankStatement).where(BankStatement.pdf_content_hash == removed_hash))
    )
    with patch("ingestion_worker.duplicates.removal.vector_store.delete_embeddings", return_value=True) as delete:
        result = removal.process_next_removal(db_session, sleep=lambda _s: None)

    assert result.status == "completed"
    assert sorted(delete.call_args.args[1]) == removed_ids  # exactly the removed copy's transactions
    assert db_session.query(BankStatement).count() == 1 and db_session.query(Transaction).count() == 5
    assert db_session.scalar(select(BankStatement.pdf_content_hash)) == kept_hash  # the statement is counted once now
    db_session.refresh(pair)
    assert pair.status is DuplicatePairStatus.REMOVED
    job = db_session.query(StatementRemovalJob).one()
    assert job.status is StatementRemovalJobStatus.COMPLETED

    # 4. The next ingestion run: the kept file is an exact duplicate (as today); the removed copy's file is
    #    recognised from memory and NOT read again (no Gemini call), and is not re-ingested.
    extract_calls = []
    run2, extract_mock = _run(db_session, lambda pdf: extract_calls.append(pdf) or statement)
    assert extract_mock.call_count == 0 and extract_calls == []
    outcomes = {f.drive_file_name: f.outcome for f in db_session.query(IngestionRunFile).filter_by(ingestion_run_id=run2.id)}
    kept_name = "JUN 2026_0728.pdf" if kept_hash == hashlib.sha256(FIRST).hexdigest() else "JUN 2026_0828.pdf"
    removed_name = "JUN 2026_0828.pdf" if kept_name == "JUN 2026_0728.pdf" else "JUN 2026_0728.pdf"
    assert outcomes[kept_name] is IngestionRunFileOutcome.SKIPPED_DUPLICATE
    assert outcomes[removed_name] is IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
    assert run2.files_skipped_count == 2 and run2.files_failed_count == 0 and run2.status == IngestionRunStatus.COMPLETED
    assert db_session.query(BankStatement).count() == 1  # still counted once
    assert repository.get_known_file(db_session, removed_hash).state.value == "confirmed_duplicate"


def test_overriding_a_removed_copy_brings_it_back_on_the_next_run(db_session, monkeypatch):
    """BR-41: a removed copy can be overridden; its file is then ingested on the next run."""
    for name in ("Groceries", "UNSURE"):
        db_session.add(Category(name=name, active=True, is_reserved=(name == "UNSURE")))
    db_session.flush()
    statement = extracted(june(5), bank="UOB")
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", False)
    _run(db_session, lambda _pdf: statement)
    monkeypatch.setattr(config.settings, "duplicate_detection_enabled", True)
    service.run_pair_scan(db_session)
    (pair,) = db_session.query(DuplicatePair).all()
    removed_hash = pair.hash_a if pair.hash_b == pair.keep_hash else pair.hash_b
    db_session.add(StatementRemovalJob(pair_id=pair.id, remove_statement_hash=removed_hash, corrections_acknowledged=0))
    db_session.flush()
    with patch("ingestion_worker.duplicates.removal.vector_store.delete_embeddings", return_value=True):
        removal.process_next_removal(db_session, sleep=lambda _s: None)
    assert db_session.query(BankStatement).count() == 1

    known = repository.get_known_file(db_session, removed_hash)  # what the API's override does
    known.state = type(known.state).OVERRIDDEN
    db_session.flush()
    run, _ = _run(db_session, lambda _pdf: statement)

    assert db_session.query(BankStatement).count() == 2  # the removed copy is back
    assert run.files_processed_count == 1
