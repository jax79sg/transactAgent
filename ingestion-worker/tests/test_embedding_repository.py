import uuid
from datetime import date
from decimal import Decimal

from ingestion_worker.embedding import repository
from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    EmbeddingStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    Transaction,
)


def _make_category(db, name=None):
    category = Category(name=name or f"Category {uuid.uuid4().hex[:8]}", active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description="NTUC FAIRPRICE", **overrides):
    category = overrides.pop("category", None) or _make_category(db)
    statement = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 1),
        description=description,
        out_flow=Decimal("10.00"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
        **overrides,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_recurring_payment(db, name="Gym Membership", **overrides):
    payment = RecurringPayment(
        name=name,
        expected_amount=Decimal("80.00"),
        frequency=RecurringPaymentFrequency.MONTHLY,
        due_day=15,
        **overrides,
    )
    db.add(payment)
    db.flush()
    return payment


class TestListPendingTransactions:
    def test_only_returns_pending_rows(self, db_session):
        pending = _make_transaction(db_session, "PENDING ONE")
        completed = _make_transaction(db_session, "ALREADY DONE", embedding_status=EmbeddingStatus.COMPLETED)

        result = repository.list_pending_transactions(db_session, limit=10)

        ids = {t.id for t in result}
        assert pending.id in ids
        assert completed.id not in ids

    def test_respects_limit(self, db_session):
        for i in range(3):
            _make_transaction(db_session, f"MERCHANT {i}")

        result = repository.list_pending_transactions(db_session, limit=2)

        assert len(result) == 2

    def test_deterministic_order_by_created_at_then_id(self, db_session):
        """WR-26/NFR-4: an interrupted-and-resumed batch must make visible forward
        progress, not reprocess an arbitrary subset. `created_at` is set explicitly
        here rather than relying on `server_default=func.now()` -- within a single
        Postgres transaction (as this test fixture uses), `now()` is frozen at
        transaction start, so two rows inserted back-to-back would otherwise get
        IDENTICAL created_at values, making insertion order untestable through the
        ORM default alone (caught by actually running this against Postgres, not
        assumed)."""
        from datetime import datetime, timedelta, timezone

        earlier = datetime.now(timezone.utc) - timedelta(minutes=5)
        later = datetime.now(timezone.utc)
        first = _make_transaction(db_session, "FIRST", created_at=earlier)
        second = _make_transaction(db_session, "SECOND", created_at=later)

        result = repository.list_pending_transactions(db_session, limit=10)

        assert [t.id for t in result] == [first.id, second.id]


class TestListPendingRecurringPayments:
    def test_only_returns_pending_rows(self, db_session):
        pending = _make_recurring_payment(db_session, "Pending Payment")
        completed = _make_recurring_payment(db_session, "Done Payment", embedding_status=EmbeddingStatus.COMPLETED)

        result = repository.list_pending_recurring_payments(db_session, limit=10)

        ids = {p.id for p in result}
        assert pending.id in ids
        assert completed.id not in ids


class TestMarkEmbedded:
    def test_mark_transaction_embedded_sets_completed(self, db_session):
        txn = _make_transaction(db_session)
        assert txn.embedding_status == EmbeddingStatus.PENDING

        repository.mark_transaction_embedded(db_session, txn)
        db_session.refresh(txn)

        assert txn.embedding_status == EmbeddingStatus.COMPLETED

    def test_mark_recurring_payment_embedded_sets_completed(self, db_session):
        payment = _make_recurring_payment(db_session)
        assert payment.embedding_status == EmbeddingStatus.PENDING

        repository.mark_recurring_payment_embedded(db_session, payment)
        db_session.refresh(payment)

        assert payment.embedding_status == EmbeddingStatus.COMPLETED
