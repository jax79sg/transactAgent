"""Shared fixtures for the Backfill Tool tests: an in-memory fake Drive and realistic seed
data (statements with manual corrections and every kind of dependent row)."""

import hashlib
import json
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from transactagent_db.models import (
    BankStatement,
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    Category,
    CategorySource,
    IngestionRun,
    IngestionRunFile,
    IngestionRunFileOutcome,
    IngestionRunStatus,
    RecategorizationJob,
    RecategorizationJobStatus,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    Transaction,
    User,
)

from ingestion_worker.clients.drive_client import DriveFileRef


class FakeDrive:
    """In-memory stand-in for the drive_client functions the Backfill Tool and the pipeline call."""

    def __init__(self):
        self.pdfs: dict[str, tuple[str, bytes]] = {}
        self.nodes: dict[str, dict] = {}
        self._counter = 0
        self.corrupt_downloads_of: set[str] = set()  # file names whose DOWNLOAD returns damaged bytes

    def add_pdf(self, file_id: str, name: str, content: bytes) -> None:
        self.pdfs[file_id] = (name, content)

    def _new_id(self) -> str:
        self._counter += 1
        return f"drive-node-{self._counter}"

    def _ensure(self, name: str, parent: str) -> str:
        for node_id, node in self.nodes.items():
            if node["name"] == name and node["parent"] == parent and node["content"] is None:
                return node_id
        node_id = self._new_id()
        self.nodes[node_id] = {"name": name, "parent": parent, "content": None}
        return node_id

    def list_folder_pdf_files(self, db):
        return [DriveFileRef(id=i, name=n) for i, (n, _) in self.pdfs.items()]

    def ensure_backup_folder_exists(self, db, parent):
        return self._ensure("backup", parent)

    def ensure_subfolder(self, db, parent, name):
        return self._ensure(name, parent)

    def upload_file(self, db, folder_id, filename, content, mime_type):
        node_id = self._new_id()
        self.nodes[node_id] = {"name": filename, "parent": folder_id, "content": content}
        return DriveFileRef(id=node_id, name=filename)

    def list_backup_folder_files(self, db, folder_id):
        return [DriveFileRef(id=i, name=n["name"]) for i, n in self.nodes.items() if n["parent"] == folder_id]

    def download_file(self, db, ref):
        if ref.id in self.pdfs:
            return self.pdfs[ref.id][1]
        node = self.nodes[ref.id]
        content = node["content"]
        if node["name"] in self.corrupt_downloads_of:
            return content + b"CORRUPTED"
        return content

    def files_in(self, folder_name: str) -> dict[str, bytes]:
        folder_id = next(i for i, n in self.nodes.items() if n["name"] == folder_name and n["content"] is None)
        return {n["name"]: n["content"] for n in self.nodes.values() if n["parent"] == folder_id}

    def folder_names(self) -> list[str]:
        return [n["name"] for n in self.nodes.values() if n["content"] is None]

    def patched(self) -> ExitStack:
        stack = ExitStack()
        for name in (
            "list_folder_pdf_files", "ensure_backup_folder_exists", "ensure_subfolder",
            "upload_file", "list_backup_folder_files", "download_file",
        ):
            stack.enter_context(patch(f"ingestion_worker.clients.drive_client.{name}", side_effect=getattr(self, name)))
        return stack


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def add_txn(db, statement, category, description, day, amount, *, direction="out", source=CategorySource.SIMILARITY):
    txn = Transaction(
        bank_statement_id=statement.id, transaction_date=day, description=description,
        out_flow=Decimal(amount) if direction == "out" else None,
        in_flow=Decimal(amount) if direction == "in" else None,
        currency="SGD", bank_name=statement.bank_name, category_id=category.id, category_source=source,
    )
    db.add(txn)
    db.flush()
    return txn


def seed_legacy(db, drive: FakeDrive) -> SimpleNamespace:
    """Three pre-backfill statements (no sections): two re-ingestible, one whose PDF is gone from
    Drive; 4+1+1 transactions of which 3 are manual corrections (two of them identical rows' twin);
    and one of each kind of dependent row."""
    unsure = Category(name="UNSURE", active=True, is_reserved=True)
    groceries, dining = Category(name="Groceries", active=True), Category(name="Dining", active=True)
    user = User(username="owner", password_hash="x")
    db.add_all([unsure, groceries, dining, user])
    db.flush()

    pdf1, pdf2 = b"PDF-ONE", b"PDF-TWO"
    drive.add_pdf("pdf-1", "jan-ocbc.pdf", pdf1)
    drive.add_pdf("pdf-2", "feb-trust.pdf", pdf2)
    s1 = BankStatement(drive_file_id="pdf-1", pdf_content_hash=sha256(pdf1), bank_name="OCBC Bank")
    s2 = BankStatement(drive_file_id="pdf-2", pdf_content_hash=sha256(pdf2), bank_name="Trust Bank")
    s3 = BankStatement(drive_file_id="pdf-gone", pdf_content_hash=sha256(b"GONE"), bank_name="HSBC")
    db.add_all([s1, s2, s3])
    db.flush()

    ntuc = add_txn(db, s1, dining, "NTUC", date(2026, 1, 15), "25.50", source=CategorySource.MANUAL)
    coffee = add_txn(db, s1, groceries, "COFFEE", date(2026, 1, 16), "4.50")
    mrt_manual = add_txn(db, s1, dining, "MRT", date(2026, 1, 17), "2.00", source=CategorySource.MANUAL)
    mrt_auto = add_txn(db, s1, groceries, "MRT", date(2026, 1, 17), "2.00")
    salary = add_txn(db, s2, dining, "SALARY", date(2026, 2, 1), "3000", direction="in", source=CategorySource.MANUAL)
    gone = add_txn(db, s3, dining, "GONE", date(2026, 3, 1), "9.99", source=CategorySource.MANUAL)

    job = RecategorizationJob(source_transaction_id=ntuc.id, status=RecategorizationJobStatus.COMPLETED)
    gone_job = RecategorizationJob(source_transaction_id=gone.id, status=RecategorizationJobStatus.COMPLETED)
    db.add_all([job, gone_job])
    db.flush()
    db.add_all([
        RecategorizationProposal(recategorization_job_id=job.id, candidate_transaction_id=coffee.id,
                                 proposed_category_id=dining.id, match_score=Decimal("88.00"),
                                 source_bucket=RecategorizationProposalSourceBucket.UNSURE,
                                 status=RecategorizationProposalStatus.PENDING),
        # a proposal whose JOB is in the wipe set but whose candidate is in the KEPT statement
        RecategorizationProposal(recategorization_job_id=job.id, candidate_transaction_id=gone.id,
                                 proposed_category_id=dining.id, match_score=Decimal("90.00"),
                                 source_bucket=RecategorizationProposalSourceBucket.CATEGORIZED,
                                 status=RecategorizationProposalStatus.PENDING),
        CategorizationDisagreement(transaction_id=coffee.id, similarity_category_id=dining.id,
                                   llm_category_id=groceries.id, similarity_score=Decimal("70.00"),
                                   status=CategorizationDisagreementStatus.PENDING),
        CategorizationDisagreement(transaction_id=gone.id, similarity_category_id=dining.id,
                                   llm_category_id=groceries.id, similarity_score=Decimal("70.00"),
                                   status=CategorizationDisagreementStatus.PENDING),
    ])
    payment = RecurringPayment(name="Gym", expected_amount=Decimal("80.00"), frequency=RecurringPaymentFrequency.MONTHLY, due_day=15)
    db.add(payment)
    db.flush()
    db.add_all([
        RecurringPaymentMatch(recurring_payment_id=payment.id, transaction_id=ntuc.id, cycle_period="2026-01",
                              status=RecurringPaymentMatchStatus.PENDING, amount_at_match=Decimal("25.50")),
        RecurringPaymentMatch(recurring_payment_id=payment.id, transaction_id=gone.id, cycle_period="2026-03",
                              status=RecurringPaymentMatchStatus.PENDING, amount_at_match=Decimal("9.99")),
    ])
    old_run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
    db.add(old_run)
    db.flush()
    run_file = IngestionRunFile(ingestion_run_id=old_run.id, drive_file_id="pdf-1", drive_file_name="jan-ocbc.pdf",
                                outcome=IngestionRunFileOutcome.PROCESSED, bank_statement_id=s1.id)
    db.add(run_file)
    db.flush()
    return SimpleNamespace(
        s1=s1, s2=s2, s3=s3, ntuc=ntuc, coffee=coffee, mrt_manual=mrt_manual, mrt_auto=mrt_auto,
        salary=salary, gone=gone, categories=SimpleNamespace(dining=dining, groceries=groceries, unsure=unsure),
        run_file=run_file, user=user,
    )


def txn_json(description, day, amount, direction="out"):
    return {"transaction_date": day, "description": description, "amount": float(amount), "direction": direction,
            "printed_converted_amount_sgd": None, "confidence": "high"}


# What the (mocked) extraction returns when the two re-ingestible PDFs are re-read.
JAN_RESPONSE = json.dumps({
    "bank_name": "OCBC Bank", "currency": "SGD", "confidence": "high", "statement_date": "2026-01-31",
    "sections": [{"account_identifier": "501-123-456", "account_type": "deposit", "closing_balance": 900.0,
                  "closing_balance_date": "2026-01-31",
                  "transactions": [txn_json("NTUC", "2026-01-15", 25.5), txn_json("COFFEE", "2026-01-16", 4.5),
                                   txn_json("MRT", "2026-01-17", 2), txn_json("MRT", "2026-01-17", 2)]}],
})
FEB_RESPONSE = json.dumps({
    "bank_name": "Trust Bank", "currency": "SGD", "confidence": "high", "statement_date": "2026-02-28",
    "sections": [
        {"account_identifier": "9988", "account_type": "deposit",
         "transactions": [txn_json("SALARY", "2026-02-01", 3000, "in")]},
        {"account_identifier": "4111", "account_type": "credit_card",
         "transactions": [txn_json("AMAZON", "2026-02-10", 12)]},
    ],
})
