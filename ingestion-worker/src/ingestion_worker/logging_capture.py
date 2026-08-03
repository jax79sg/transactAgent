"""Captures live worker log output into ingestion_run_logs while a run is active, for
the frontend's live log-tail view (added 2026-08-02 -- see aidlc-docs/audit.md).

Attached to the root logger at worker startup, so it captures everything, not just
ingestion_worker's own log calls -- including googleapiclient, httpx, openai's client,
and google-genai's messages, matching what a user watching `docker compose logs` would
actually see.
"""

import logging
import traceback

from ingestion_worker.db import SessionLocal
from transactagent_db.models import IngestionRunLog

_current_run_id: str | None = None


def set_current_run(run_id) -> None:
    """WR-8: the worker only ever processes one run at a time, so a single module-level
    value (not per-thread/per-task state) is sufficient to track "which run, if any, is
    currently active" for log attribution."""
    global _current_run_id
    _current_run_id = str(run_id) if run_id is not None else None


class DbLogHandler(logging.Handler):
    """Writes each log record to ingestion_run_logs if a run is currently active.

    Uses its own short-lived session per record rather than the run's own processing
    session: log capture must never affect, or be affected by, the run's own
    transaction -- a run that ultimately fails and rolls back other changes should
    still keep its log trail, and a failure writing a log line must never break the
    pipeline itself (standard logging.Handler contract: emit() should never raise).
    """

    def emit(self, record: logging.LogRecord) -> None:
        run_id = _current_run_id
        if run_id is None:
            return
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{''.join(traceback.format_exception(*record.exc_info))}"
            with SessionLocal() as session:
                session.add(
                    IngestionRunLog(
                        ingestion_run_id=run_id,
                        level=record.levelname,
                        logger_name=record.name,
                        message=message,
                    )
                )
                session.commit()
        except Exception:  # noqa: BLE001 - logging.Handler.emit() must never raise
            self.handleError(record)
