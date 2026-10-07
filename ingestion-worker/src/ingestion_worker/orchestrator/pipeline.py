"""The Ingestion Orchestrator pipeline (business-logic-model.md). Ties together the
Drive Connector, Duplicate Detection, Statement Extraction, Categorization Engine, and
Currency Conversion components. NFR-2.2 / WR-8: one file's failure never aborts the
run; only one run is ever processed at a time.
"""

import logging

from sqlalchemy.orm import Session
from transactagent_db.models import IngestionRunFileOutcome, KnownFileState, Transaction

from ingestion_worker.accounts.service import resolve_sections
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
from ingestion_worker.duplicates import service as duplicates_service
from ingestion_worker.extraction.service import ExtractionFailure, extract_statement
from ingestion_worker.logging_capture import set_current_run
from ingestion_worker.orchestrator import repository as orchestrator_repository
from ingestion_worker.recurring_payments import service as recurring_payments_service

logger = logging.getLogger(__name__)


def process_run(db: Session, run, *, backfill_mode: bool = False) -> None:
    """`backfill_mode` (Epic 14, WR-62/WR-69): used only by the Backfill Tool's reingest. The
    probable-duplicate check then runs whatever the detection switch says, and a match whose sizes
    clearly differ is NOT skipped, so a larger statement's extra transactions are never silently
    dropped in the mode that otherwise resolves duplicates automatically."""
    set_current_run(run.id)
    try:
        _process_run(db, run, backfill_mode=backfill_mode)
    finally:
        set_current_run(None)


def _process_run(db: Session, run, *, backfill_mode: bool = False) -> None:
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
            # Epic 13: a SAVEPOINT around the file, so that if it fails unexpectedly only ITS
            # writes are discarded (see the except block below). update_run_progress() at the
            # end of _process_one_file commits and so releases the savepoint on every normal
            # path; the savepoint is still active only when the file blew up midway.
            file_savepoint = db.begin_nested()
            try:
                _process_one_file(db, run, file_ref, backfill_mode=backfill_mode)
            except Exception:
                if file_savepoint.is_active:
                    file_savepoint.rollback()
                raise
    except Exception:
        # leave the run stuck "running" forever.
        logger.exception("Ingestion run %s failed unexpectedly while processing files", run.id)
        # (Epic 13, found while planning its Code Generation: a file's writes are only ever
        # flushed, and fail_run() COMMITS -- so before the savepoint above, the half-written
        # statement, accounts, sections, and transactions of the file that just blew up were
        # committed along with the run's failed status, and the statement's recorded content
        # hash then made that file be skipped as a duplicate forever. The savepoint was
        # already rolled back where the exception was raised, so only the file in flight is
        # discarded -- which is what "a file is either fully processed or not started" has
        # always promised.)
        orchestrator_repository.fail_run(db, run)
        return

    logger.info("Ingestion run %s: complete", run.id)
    orchestrator_repository.complete_run(db, run)


def _process_one_file(db: Session, run, file_ref, *, backfill_mode: bool = False) -> None:
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

    # Epic 14, check 1 (WR-61): always on, before extraction. A file already judged (flagged, or a
    # removed copy whose Drive file remains) is never read by Gemini again (NFR-PD-2); a file the
    # user overrode proceeds and is exempt from check 2.
    remembered = duplicate_detection.lookup_remembered_file(db, content_hash)
    overridden = False
    if remembered is not None:
        if remembered.state == KnownFileState.OVERRIDDEN:
            overridden = True
        else:
            logger.info(
                "%s: remembered as a probable duplicate of a statement already held (%s) -- skipping without reading it",
                file_ref.name, remembered.state.value,
            )
            orchestrator_repository.record_run_file(
                db, run,
                drive_file_id=file_ref.id, drive_file_name=file_ref.name,
                outcome=IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE,
                duplicate_comparison_id=remembered.comparison_id,
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

    # Epic 14, check 2 (WR-62): after extraction and BEFORE any account, statement, section or
    # transaction is created, so a skipped file leaves nothing behind.
    if not overridden and _skip_if_probable_duplicate(db, run, file_ref, result, content_hash, backfill_mode):
        return

    logger.info(
        "%s: extracted %d transaction(s) in %d account section(s) from %s -- resolving accounts and categorizing",
        file_ref.name, len(result.transactions), len(result.sections), result.bank_name,
    )
    # Epic 13 (WR-49): resolve each account section to an account, then record the
    # statement and one statement-account row per section. All of this shares the file's
    # database transaction with the transactions below, so a file that fails later leaves
    # no orphan account or section (see the rollback in _process_run).
    resolved_sections = resolve_sections(db, result)
    statement = duplicate_detection.record_processed(
        db, drive_file_id=file_ref.id, pdf_content_hash=content_hash, bank_name=result.bank_name
    )
    statement_accounts = duplicate_detection.record_statement_accounts(db, statement, resolved_sections)

    # Each entry: (the section's currency, the section's StatementAccount id, the raw transaction).
    entries = [
        (resolved.section.currency, statement_account.id, raw_txn)
        for resolved, statement_account in zip(resolved_sections, statement_accounts, strict=True)
        for raw_txn in resolved.section.transactions
    ]

    # WR-34 (Categorization Model Fine-Tuning): converted SGD amount is now part of
    # the categorization prompt (alongside description), so conversion is resolved
    # here, upfront per transaction -- moved earlier than its previous call site
    # inside _persist_transaction -- and the result is reused there rather than
    # recomputed. Conversion itself has no dependency on categorization, so this
    # reordering changes nothing about its own behavior (same FX cache reads/writes,
    # just earlier in the file's processing). Epic 13 (WR-51): converted with the
    # transaction's SECTION currency, not one statement-wide currency.
    conversions = [
        resolve_converted_amount(
            db,
            amount=raw_txn.amount,
            currency=currency,
            transaction_date=raw_txn.transaction_date,
            printed_converted_amount_sgd=raw_txn.printed_converted_amount_sgd,
        )
        for currency, _statement_account_id, raw_txn in entries
    ]

    # WR-27 (Matching Precision Refinement): every transaction gets classified by
    # the LLM, always -- one upfront, concurrent batch call per file, before the
    # per-transaction persistence loop, rather than a per-transaction last resort.
    # Epic 13: still ONE batch per file, across every account section.
    llm_category_by_description = classify_batch(
        db,
        [
            (raw_txn.description, conversion.converted_amount_sgd)
            for (_currency, _statement_account_id, raw_txn), conversion in zip(entries, conversions, strict=True)
        ],
    )

    for (currency, statement_account_id, raw_txn), conversion in zip(entries, conversions, strict=True):
        _persist_transaction(
            db,
            statement,
            currency,
            raw_txn,
            llm_category_by_description.get(raw_txn.description, UNSURE_NAME),
            conversion,
            statement_account_id=statement_account_id,
        )

    logger.info("%s: done", file_ref.name)
    orchestrator_repository.record_run_file(
        db, run,
        drive_file_id=file_ref.id, drive_file_name=file_ref.name,
        outcome=IngestionRunFileOutcome.PROCESSED, bank_statement_id=statement.id,
        transactions_extracted_count=len(entries),
    )
    orchestrator_repository.update_run_progress(db, run, processed_delta=1)


def _skip_if_probable_duplicate(db: Session, run, file_ref, result, content_hash: str, backfill_mode: bool) -> bool:
    """WR-62. Returns True when the file was recorded as a probable duplicate and must not be ingested.

    Fails open: if judging or recording raises, a warning (and so a run-log line) is written and the
    file ingests as it did before this feature, because a failed duplicate check must never block a
    statement from being ingested. Everything happens inside a savepoint, so a database error here
    cannot poison the file's own transaction."""
    try:
        comparison = None
        with db.begin_nested():
            match = duplicates_service.find_probable_duplicate_of(
                db, result, content_hash, file_name=file_ref.name, force_enabled=backfill_mode
            )
            if match is not None:
                if backfill_mode and not match.verdict.sizes_comparable:
                    logger.info(
                        "%s: matches a held statement but the sizes differ clearly -- NOT skipped in the backfill; "
                        "it will be listed for review instead", file_ref.name,
                    )
                else:
                    comparison = duplicates_service.record_skipped_duplicate(db, match, content_hash)
    except Exception:
        logger.warning("%s: the duplicate check failed -- ingesting the file as usual", file_ref.name, exc_info=True)
        return False
    if comparison is None:
        return False
    logger.info("%s: probable duplicate of %s -- skipped. %s", file_ref.name, match.held.file_name or match.held.bank_name or "a held statement", match.draft.reason)
    orchestrator_repository.record_run_file(
        db, run,
        drive_file_id=file_ref.id, drive_file_name=file_ref.name,
        outcome=IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE,
        duplicate_comparison_id=comparison.id,
        transactions_extracted_count=len(result.transactions),
    )
    orchestrator_repository.update_run_progress(db, run, skipped_delta=1)
    return True


def _persist_transaction(
    db: Session, statement, currency: str, raw_txn, llm_category: str, conversion, *, statement_account_id=None
) -> Transaction:
    # WR-36: "outflow"/"inflow", mirroring categorization/service.py's _transaction_direction
    # -- raw_txn has no Transaction row yet at this point, so it's derived from
    # raw_txn.direction.value ("out"/"in") rather than out_flow/in_flow.
    direction = "outflow" if raw_txn.direction.value == "out" else "inflow"
    categorization = categorize(db, raw_txn.description, raw_txn.amount, direction, llm_category)
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
        # Epic 13 (WR-51, BR-38): the account section this transaction was printed under.
        statement_account_id=statement_account_id,
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
