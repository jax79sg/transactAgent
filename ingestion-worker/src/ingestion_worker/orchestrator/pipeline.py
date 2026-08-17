"""The Ingestion Orchestrator pipeline (business-logic-model.md). Ties together the
Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, and
Currency Conversion components. NFR-2.2 / WR-8: one file's failure never aborts the
run; only one run is ever processed at a time.
"""

import logging

from sqlalchemy.orm import Session
from transactagent_db.models import IngestionRunFileOutcome, Transaction

from ingestion_worker.categorization import repository as categorization_repository
from ingestion_worker.categorization.service import (
    UNSURE_NAME,
    categorize,
    classify_batch,
    recategorize_unsure_from_precedent,
)
from ingestion_worker.clients import drive_client
from ingestion_worker.clients.drive_client import (
    DriveNotConnectedError,
    DriveReauthRequiredError,
)
from ingestion_worker.clients.retry import TransientError
from ingestion_worker.currency.service import resolve_converted_amount
from ingestion_worker.duplicate_detection import service as duplicate_detection
from ingestion_worker.extraction.service import ExtractionFailure, extract_statement
from ingestion_worker.logging_capture import set_current_run
from ingestion_worker.orchestrator import repository as orchestrator_repository
from ingestion_worker.recurring_payments import service as recurring_payments_service

logger = logging.getLogger(__name__)


def process_run(db: Session, run) -> None:
    set_current_run(run.id)
    try:
        _process_run(db, run)
    finally:
        set_current_run(None)


def _process_run(db: Session, run) -> None:
    logger.info("Ingestion run %s: listing PDF files in the Drive folder", run.id)
    try:
        files = drive_client.list_folder_pdf_files(db)
    except (DriveNotConnectedError, DriveReauthRequiredError, TransientError) as exc:
        # Run-level failure (US-1.1 edge case): no files could even be listed.
        logger.warning("Ingestion run %s failed at Drive listing: %s", run.id, exc)
        orchestrator_repository.fail_run(db, run)
        return
    except Exception:
        # HttpError, such as the Drive API being disabled on the Google Cloud project) must
        # still resolve the run to a terminal status. Leaving it "running" would permanently
        # block every future run via ingestion_runs' single-active-run unique constraint, since
        # nothing ever revisits a stuck "running" row -- caught for real via a run that got
        # stuck this way (see aidlc-docs/audit.md).
        logger.exception("Ingestion run %s failed at Drive listing with an unexpected error", run.id)
        orchestrator_repository.fail_run(db, run)
        return

    logger.info("Ingestion run %s: found %d file(s)", run.id, len(files))
    orchestrator_repository.update_run_progress(db, run, files_found=len(files))

    try:
        for index, file_ref in enumerate(files, start=1):
            # Checked between files, never mid-file -- a file is either fully
            # processed or not started, so this can't leave a half-written
            # statement/transaction behind. cancel_requested_at is written only by
            # the API (a separate process); status is written only here, so the two
            # never race on the same column (see aidlc-docs/audit.md 2026-08-05).
            if orchestrator_repository.is_cancellation_requested(db, run.id):
                logger.info(
                    "Ingestion run %s: cancellation requested, stopping before file %d/%d", run.id, index, len(files)
                )
                orchestrator_repository.cancel_run(db, run)
                return
            logger.info("Ingestion run %s: processing file %d/%d: %s", run.id, index, len(files), file_ref.name)
            _process_one_file(db, run, file_ref)
    except Exception:
        # leave the run stuck "running" forever.
        logger.exception("Ingestion run %s failed unexpectedly while processing files", run.id)
        orchestrator_repository.fail_run(db, run)
        return

    logger.info("Ingestion run %s: complete", run.id)
    orchestrator_repository.complete_run(db, run)


def _process_one_file(db: Session, run, file_ref) -> None:
    try:
        pdf_bytes = drive_client.download_file(db, file_ref)
    except (DriveNotConnectedError, DriveReauthRequiredError, TransientError) as exc:
        orchestrator_repository.record_run_file(
            db, run,
            drive_file_id=file_ref.id, drive_file_name=file_ref.name,
            outcome=IngestionRunFileOutcome.FAILED, failure_reason=f"Download failed: {exc}",
        )
        orchestrator_repository.update_run_progress(db, run, failed_delta=1)
        return

    content_hash = duplicate_detection.compute_file_hash(pdf_bytes)
    existing = duplicate_detection.find_existing_statement(db, content_hash)
    if existing is not None:
        logger.info("%s: already processed (duplicate content hash) -- skipping", file_ref.name)
        orchestrator_repository.record_run_file(
            db, run,
            drive_file_id=file_ref.id, drive_file_name=file_ref.name,
            outcome=IngestionRunFileOutcome.SKIPPED_DUPLICATE, bank_statement_id=existing.id,
        )
        orchestrator_repository.update_run_progress(db, run, skipped_delta=1)
        return

    logger.info("%s: extracting statement contents", file_ref.name)
    result = extract_statement(pdf_bytes)
    if isinstance(result, ExtractionFailure):
        logger.warning("%s: extraction failed: %s", file_ref.name, result.reason)
        orchestrator_repository.record_run_file(
            db, run,
            drive_file_id=file_ref.id, drive_file_name=file_ref.name,
            outcome=IngestionRunFileOutcome.FAILED, failure_reason=result.reason,
            raw_extracted_text=result.raw_response,
        )
        orchestrator_repository.update_run_progress(db, run, failed_delta=1)
        return

    logger.info("%s: extracted %d transaction(s) from %s -- categorizing", file_ref.name, len(result.transactions), result.bank_name)
    statement = duplicate_detection.record_processed(
        db, drive_file_id=file_ref.id, pdf_content_hash=content_hash, bank_name=result.bank_name
    )

    # WR-34 (Categorization Model Fine-Tuning): converted SGD amount is now part of
    # the categorization prompt (alongside description), so conversion is resolved
    # here, upfront per transaction -- moved earlier than its previous call site
    # inside _persist_transaction -- and the result is reused there rather than
    # recomputed. Conversion itself has no dependency on categorization, so this
    # reordering changes nothing about its own behavior (same FX cache reads/writes,
    # just earlier in the file's processing).
    conversions = [
        resolve_converted_amount(
            db,
            amount=raw_txn.amount,
            currency=result.currency,
            transaction_date=raw_txn.transaction_date,
            printed_converted_amount_sgd=raw_txn.printed_converted_amount_sgd,
        )
        for raw_txn in result.transactions
    ]

    # WR-27 (Matching Precision Refinement): every transaction gets classified by
    # the LLM, always -- one upfront, concurrent batch call per file, before the
    # per-transaction persistence loop, rather than a per-transaction last resort.
    llm_category_by_description = classify_batch(
        db,
        [
            (raw_txn.description, conversion.converted_amount_sgd)
            for raw_txn, conversion in zip(result.transactions, conversions, strict=True)
        ],
    )

    for raw_txn, conversion in zip(result.transactions, conversions, strict=True):
        _persist_transaction(
            db,
            statement,
            result.currency,
            raw_txn,
            llm_category_by_description.get(raw_txn.description, UNSURE_NAME),
            conversion,
        )

    logger.info("%s: done", file_ref.name)
    orchestrator_repository.record_run_file(
        db, run,
        drive_file_id=file_ref.id, drive_file_name=file_ref.name,
        outcome=IngestionRunFileOutcome.PROCESSED, bank_statement_id=statement.id,
        transactions_extracted_count=len(result.transactions),
    )
    orchestrator_repository.update_run_progress(db, run, processed_delta=1)


def _persist_transaction(db: Session, statement, currency: str, raw_txn, llm_category: str, conversion) -> Transaction:
    categorization = categorize(db, raw_txn.description, raw_txn.amount, llm_category)
    category = categorization_repository.find_category_by_name(db, categorization.category_name)
    # find_category_by_name always resolves here: categorize() only ever returns a
    # whitelist name or "UNSURE", both of which are guaranteed to exist as Category rows.
    llm_suggested_category = (
        categorization_repository.find_category_by_name(db, categorization.llm_suggested_category_name)
        if categorization.llm_suggested_category_name
        else None
    )  # BR-26: null when the LLM abstained or its endpoint was unreachable

    # WR-34: conversion is now resolved upfront by the caller (alongside every other
    # transaction in the file, before classify_batch), not here -- reused, not
    # recomputed.

    transaction = Transaction(
        bank_statement_id=statement.id,
        transaction_date=raw_txn.transaction_date,
        description=raw_txn.description,
        out_flow=raw_txn.amount if raw_txn.direction.value == "out" else None,
        in_flow=raw_txn.amount if raw_txn.direction.value == "in" else None,
        currency=currency,
        bank_name=statement.bank_name,
        category_id=category.id,
        category_source=categorization.source,
        llm_suggested_category_id=llm_suggested_category.id if llm_suggested_category else None,
        converted_amount_sgd=conversion.converted_amount_sgd,
        conversion_is_approximate=conversion.is_approximate,
        conversion_unavailable=conversion.is_unavailable,
        fx_rate_used_id=conversion.fx_rate_id,
    )
    db.add(transaction)
    db.flush()

    # WR-28 (Matching Precision Refinement): a genuine disagreement needs the new
    # transaction's real id, which only exists after the flush above -- record it
    # here, not inside categorize() itself (domain-entities.md's DisagreementInfo).
    if categorization.disagreement is not None:
        similarity_category = categorization_repository.find_category_by_name(
            db, categorization.disagreement.similarity_category_name
        )
        llm_disagreement_category = categorization_repository.find_category_by_name(
            db, categorization.disagreement.llm_category_name
        )
        categorization_repository.record_disagreement(
            db,
            transaction_id=transaction.id,
            similarity_category_id=similarity_category.id,
            llm_category_id=llm_disagreement_category.id,
            similarity_score=categorization.disagreement.similarity_score,
        )

    # WR-16 (Epic 8): matching runs the instant a transaction exists, not on a
    # separate pass -- this is exactly that moment.
    recurring_payments_service.match_new_transaction(db, transaction)

    return transaction


def process_recategorize_job(db: Session, job) -> None:
    try:
        updated_ids = recategorize_unsure_from_precedent(db, job.id, job.source_transaction_id)
        orchestrator_repository.complete_recategorize_job(db, job, len(updated_ids))
    except Exception as exc:  # noqa: BLE001 - a failed recategorization job never affects the original manual correction (already committed independently)
        logger.warning("Recategorization job %s failed: %s", job.id, exc)
        orchestrator_repository.fail_recategorize_job(db, job)
