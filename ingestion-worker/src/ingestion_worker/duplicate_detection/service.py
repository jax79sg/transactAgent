"""Duplicate statement prevention (FR-3.1/3.2/3.3, BR-3). Hashes raw PDF bytes."""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session
from transactagent_db.models import BankStatement, KnownFile, StatementAccount

from ingestion_worker.accounts.service import ResolvedSection


def compute_file_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def find_existing_statement(db: Session, pdf_content_hash: str) -> BankStatement | None:
    return db.scalar(select(BankStatement).where(BankStatement.pdf_content_hash == pdf_content_hash))


def lookup_remembered_file(db: Session, pdf_content_hash: str) -> KnownFile | None:
    """Epic 14 (WR-61): the remembered decision for this file's content, if any. Called after the
    exact-bytes check finds nothing and BEFORE extraction, whether or not detection is switched on:
    it honours decisions the user already made (a flagged file, a removed copy, an override). One
    indexed lookup by content hash (BR-39)."""
    return db.scalar(select(KnownFile).where(KnownFile.pdf_content_hash == pdf_content_hash))


def record_processed(db: Session, *, drive_file_id: str, pdf_content_hash: str, bank_name: str) -> BankStatement:
    statement = BankStatement(drive_file_id=drive_file_id, pdf_content_hash=pdf_content_hash, bank_name=bank_name)
    db.add(statement)
    db.flush()
    return statement


def record_statement_accounts(
    db: Session, statement: BankStatement, resolved_sections: list[ResolvedSection]
) -> list[StatementAccount]:
    """Epic 13 (WR-51): one StatementAccount per resolved account section -- the account
    and, if the extraction kept one (WR-47), its closing balance and date. Returned in
    the same order as `resolved_sections`, so the caller can link each section's
    transactions to its row. BR-37 (an account at most once per statement) is already
    satisfied: the Account Resolver collapses same-account sections before this."""
    rows = [
        StatementAccount(
            bank_statement_id=statement.id,
            account_id=resolved.account.id,
            closing_balance=resolved.section.closing_balance,
            closing_balance_date=resolved.section.closing_balance_date,
        )
        for resolved in resolved_sections
    ]
    db.add_all(rows)
    db.flush()
    return rows
