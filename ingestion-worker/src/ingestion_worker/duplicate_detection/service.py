"""Duplicate statement prevention (FR-3.1/3.2/3.3, BR-3). Hashes raw PDF bytes."""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import BankStatement


def compute_file_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def find_existing_statement(db: Session, pdf_content_hash: str) -> BankStatement | None:
    return db.scalar(select(BankStatement).where(BankStatement.pdf_content_hash == pdf_content_hash))


def record_processed(db: Session, *, drive_file_id: str, pdf_content_hash: str, bank_name: str) -> BankStatement:
    statement = BankStatement(drive_file_id=drive_file_id, pdf_content_hash=pdf_content_hash, bank_name=bank_name)
    db.add(statement)
    db.flush()
    return statement
