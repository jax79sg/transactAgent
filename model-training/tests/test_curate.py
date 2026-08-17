"""curate_dataset()'s orchestration logic: split ratio, null-amount exclusion
(MTR-2), JSONL export shape (MTR-5) -- against a real Postgres (testcontainers)."""

import json
import uuid
from datetime import date
from decimal import Decimal

from transactagent_db.models import BankStatement, Category, CategorySource, Transaction

from model_training.curate import curate_dataset


def _make_category(db, name, active=True):
    category = Category(name=name, active=active, is_reserved=(name == "UNSURE"))
    db.add(category)
    db.flush()
    return category


def _make_statement(db):
    stmt = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(stmt)
    db.flush()
    return stmt


def _make_transaction(db, description, category, amount_sgd=Decimal("10.00")):
    statement = _make_statement(db)
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=Decimal("10.00"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.MANUAL,
        converted_amount_sgd=amount_sgd,
    )
    db.add(txn)
    db.flush()
    return txn


class TestCurateDataset:
    def test_splits_by_ratio(self, db_session, tmp_path):
        groceries = _make_category(db_session, "Groceries")
        for i in range(10):
            _make_transaction(db_session, f"MERCHANT {i}", groceries)

        summary = curate_dataset(db_session, tmp_path, train_split_ratio=0.8)

        assert summary.train_count == 8
        assert summary.val_count == 2

    def test_null_amount_excluded_and_counted(self, db_session, tmp_path):
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE", groceries, amount_sgd=Decimal("45.20"))
        _make_transaction(db_session, "COLD STORAGE", groceries, amount_sgd=None)

        summary = curate_dataset(db_session, tmp_path)

        assert summary.train_count + summary.val_count == 1
        assert summary.excluded_null_amount_count == 1

    def test_source_breakdown(self, db_session, tmp_path):
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE", groceries)

        summary = curate_dataset(db_session, tmp_path)

        assert summary.source_breakdown == {"manual": 1}

    def test_jsonl_shape(self, db_session, tmp_path):
        groceries = _make_category(db_session, "Groceries")
        txn = _make_transaction(db_session, "NTUC FAIRPRICE", groceries, amount_sgd=Decimal("45.20"))

        curate_dataset(db_session, tmp_path, train_split_ratio=1.0)

        lines = (tmp_path / "train.jsonl").read_text().splitlines()
        assert len(lines) == 1
        example = json.loads(lines[0])
        assert example["messages"][0]["role"] == "user"
        assert "NTUC FAIRPRICE" in example["messages"][0]["content"]
        assert "45.20 SGD" in example["messages"][0]["content"]
        assert example["messages"][1] == {"role": "assistant", "content": "Groceries"}
        assert example["_transaction_id"] == str(txn.id)
        assert example["_description"] == "NTUC FAIRPRICE"
        assert example["_amount_sgd"] == "45.20"

    def test_empty_val_split_when_ratio_is_1(self, db_session, tmp_path):
        """A 100% train ratio produces an existing-but-empty val.jsonl, not a
        missing file -- train.py should be able to rely on the file existing."""
        groceries = _make_category(db_session, "Groceries")
        _make_transaction(db_session, "NTUC FAIRPRICE", groceries)

        curate_dataset(db_session, tmp_path, train_split_ratio=1.0)

        assert (tmp_path / "val.jsonl").exists()
        assert (tmp_path / "val.jsonl").read_text() == ""
