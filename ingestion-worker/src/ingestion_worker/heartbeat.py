"""File-based liveness heartbeat (Infrastructure Design Question 1 = A).

Touched once per poll cycle; docker-compose's healthcheck checks this file's
modification recency to detect a hung or crashed worker.
"""

from pathlib import Path

from ingestion_worker.config import settings


def touch_heartbeat() -> None:
    Path(settings.heartbeat_file).touch()
