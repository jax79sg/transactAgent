"""The backfill's backup (WR-54): a Python export of every table the wipe touches, as
one JSON-lines file per table plus a checksummed manifest, uploaded to a timestamped
subfolder of the Drive backup folder and VERIFIED by downloading it back.

Rows are exported with the database's own `to_jsonb(row)`, so every column (numerics,
dates, timestamps, uuids, enums) round-trips exactly with no hand-written type
conversion; `restore` reverses it with `jsonb_populate_recordset`.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from ingestion_worker.backfill.tables import (
    BACKED_UP_TABLES,
    BACKUP_FOLDER_PREFIX,
    MANIFEST_FILE,
)
from ingestion_worker.clients import drive_client
from ingestion_worker.clients.drive_client import DriveFileRef
from ingestion_worker.config import settings

logger = logging.getLogger(__name__)


class BackupError(Exception):
    """The backup could not be built, uploaded, or verified. Nothing is wiped after this."""


@dataclass
class BackupArtifact:
    files: dict[str, bytes]  # file name -> content, including MANIFEST_FILE
    manifest: dict


@dataclass
class BackupLocation:
    folder_id: str
    folder_name: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def backup_folder_name(now: datetime | None = None) -> str:
    return f"{BACKUP_FOLDER_PREFIX}{(now or datetime.now(UTC)).strftime('%Y%m%dT%H%M%SZ')}"


def build_backup(conn: Connection, *, extra_manifest: dict) -> BackupArtifact:
    """Export every backed-up table through `conn`. The CLI passes a connection opened with
    REPEATABLE READ so all tables come from one snapshot and agree with each other and with
    the live counts taken in the same snapshot; each table's exported line count is checked
    against its own `count(*)` and the build fails on any difference."""
    files: dict[str, bytes] = {}
    tables: dict[str, dict] = {}
    for name in BACKED_UP_TABLES:  # constant list, never user input
        lines = [row[0] for row in conn.execute(text(f'SELECT to_jsonb(t)::text FROM "{name}" t ORDER BY t.id'))]
        live_count = conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
        if len(lines) != live_count:
            raise BackupError(f"{name}: exported {len(lines)} row(s) but the snapshot holds {live_count}")
        content = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        file_name = f"{name}.jsonl"
        files[file_name] = content
        tables[name] = {"row_count": live_count, "sha256": _sha256(content), "file_name": file_name}
    manifest = {"created_at": datetime.now(UTC).isoformat(), "tables": tables, **extra_manifest}
    files[MANIFEST_FILE] = json.dumps(manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
    return BackupArtifact(files=files, manifest=manifest)


def upload_backup(db: Session, artifact: BackupArtifact, folder_name: str) -> BackupLocation:
    root = drive_client.ensure_backup_folder_exists(db, settings.google_drive_backup_folder_id)
    folder_id = drive_client.ensure_subfolder(db, root, folder_name)
    for file_name, content in artifact.files.items():
        mime = "application/json" if file_name.endswith(".json") else "application/x-ndjson"
        drive_client.upload_file(db, folder_id, file_name, content, mime)
    return BackupLocation(folder_id=folder_id, folder_name=folder_name)


def _children_by_name(db: Session, folder_id: str) -> dict[str, DriveFileRef]:
    return {ref.name: ref for ref in drive_client.list_backup_folder_files(db, folder_id)}


def verify_uploaded_backup(db: Session, location: BackupLocation, artifact: BackupArtifact) -> list[str]:
    """Download every uploaded file back and compare it with what was built. Returns the
    list of problems; an empty list means the backup is verified (WR-54's gate)."""
    problems: list[str] = []
    children = _children_by_name(db, location.folder_id)
    for file_name, expected in artifact.files.items():
        ref = children.get(file_name)
        if ref is None:
            problems.append(f"{file_name}: not found in the backup folder after upload")
            continue
        downloaded = drive_client.download_file(db, ref)
        if _sha256(downloaded) != _sha256(expected):
            problems.append(f"{file_name}: downloaded content does not match what was exported")
            continue
        table = file_name.removesuffix(".jsonl")
        if table in artifact.manifest["tables"]:
            lines = downloaded.count(b"\n")
            if lines != artifact.manifest["tables"][table]["row_count"]:
                problems.append(f"{file_name}: {lines} row(s) downloaded, manifest says {artifact.manifest['tables'][table]['row_count']}")
    return problems


def find_backup_folder(db: Session, folder_name: str) -> BackupLocation:
    root = drive_client.ensure_backup_folder_exists(db, settings.google_drive_backup_folder_id)
    ref = _children_by_name(db, root).get(folder_name)
    if ref is None:
        raise BackupError(f"No backup folder named {folder_name!r} under the Drive backup folder")
    return BackupLocation(folder_id=ref.id, folder_name=folder_name)


def load_backup(db: Session, folder_name: str) -> tuple[BackupLocation, BackupArtifact]:
    """Download a backup and check every file against its manifest before anyone uses it
    (`finish` and `restore` both call this first)."""
    location = find_backup_folder(db, folder_name)
    children = _children_by_name(db, location.folder_id)
    if MANIFEST_FILE not in children:
        raise BackupError(f"{folder_name}: no {MANIFEST_FILE} found")
    manifest_bytes = drive_client.download_file(db, children[MANIFEST_FILE])
    manifest = json.loads(manifest_bytes)
    files = {MANIFEST_FILE: manifest_bytes}
    for info in manifest["tables"].values():
        ref = children.get(info["file_name"])
        if ref is None:
            raise BackupError(f"{folder_name}: {info['file_name']} is missing")
        content = drive_client.download_file(db, ref)
        if _sha256(content) != info["sha256"]:
            raise BackupError(f"{folder_name}: {info['file_name']} does not match its checksum in the manifest")
        files[info["file_name"]] = content
    return location, BackupArtifact(files=files, manifest=manifest)


def read_rows(artifact: BackupArtifact, table: str) -> list[dict]:
    """Rows of one backed-up table. Numbers are parsed as exact Decimals, never floats."""
    from decimal import Decimal

    content = artifact.files[artifact.manifest["tables"][table]["file_name"]]
    return [json.loads(line, parse_float=Decimal) for line in content.decode("utf-8").splitlines() if line]
