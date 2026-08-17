import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    EmbeddingStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    Transaction,
)

from ingestion_worker.embedding import service


def _make_category(db, name=None):
    category = Category(name=name or f"Category {uuid.uuid4().hex[:8]}", active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description="NTUC FAIRPRICE"):
    category = _make_category(db)
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
    )
    db.add(txn)
    db.flush()
    return txn


def _make_recurring_payment(db, name="Gym Membership"):
    payment = RecurringPayment(
        name=name, expected_amount=Decimal("80.00"), frequency=RecurringPaymentFrequency.MONTHLY, due_day=15
    )
    db.add(payment)
    db.flush()
    return payment


class TestProcessNextEmbeddingBatch:
    def test_processes_pending_transaction_and_marks_completed(self, db_session):
        txn = _make_transaction(db_session)

        with (
            patch("ingestion_worker.embedding.service.client.compute_embedding", return_value=[0.1, 0.2]) as mock_compute,
            patch("ingestion_worker.embedding.service.vector_store.upsert_embedding", return_value=True) as mock_upsert,
        ):
            processed = service.process_next_embedding_batch(db_session)

        assert processed == 1
        db_session.refresh(txn)
        assert txn.embedding_status == EmbeddingStatus.COMPLETED
        mock_upsert.assert_called_once_with(collection="transactions", entity_id=str(txn.id), vector=[0.1, 0.2])
        # WR-29: price-bucketed text, not the raw description alone.
        mock_compute.assert_called_once_with("NTUC FAIRPRICE | $5 to $10")

    def test_processes_pending_recurring_payment_and_marks_completed(self, db_session):
        payment = _make_recurring_payment(db_session)

        with (
            patch("ingestion_worker.embedding.service.client.compute_embedding", return_value=[0.3, 0.4]) as mock_compute,
            patch("ingestion_worker.embedding.service.vector_store.upsert_embedding", return_value=True) as mock_upsert,
        ):
            processed = service.process_next_embedding_batch(db_session)

        assert processed == 1
        db_session.refresh(payment)
        assert payment.embedding_status == EmbeddingStatus.COMPLETED
        mock_upsert.assert_called_once_with(
            collection="recurring_payment_names", entity_id=str(payment.id), vector=[0.3, 0.4]
        )
        mock_compute.assert_called_once_with("Gym Membership | $50 to $100")

    def test_processes_both_entity_types_in_one_call(self, db_session):
        txn = _make_transaction(db_session)
        payment = _make_recurring_payment(db_session)

        with (
            patch("ingestion_worker.embedding.service.client.compute_embedding", return_value=[0.1]),
            patch("ingestion_worker.embedding.service.vector_store.upsert_embedding", return_value=True),
        ):
            processed = service.process_next_embedding_batch(db_session)

        assert processed == 2
        db_session.refresh(txn)
        db_session.refresh(payment)
        assert txn.embedding_status == EmbeddingStatus.COMPLETED
        assert payment.embedding_status == EmbeddingStatus.COMPLETED

    def test_stops_early_when_embedding_endpoint_unavailable(self):
        """WR-25/26: no exception, no partial writes attempted -- returns
        immediately once the first compute_embedding call fails."""
        # A MagicMock stands in for a real Transaction row -- repository calls are
        # mocked below, so no real DB is needed for this "stop before touching
        # anything" scenario. out_flow/in_flow set to real values (not left as
        # auto-mocked attributes) since build_embedding_text (WR-29) does real
        # Decimal arithmetic on whichever is set, before compute_embedding (mocked
        # below) is ever called.
        fake_transaction = MagicMock(description="NTUC FAIRPRICE", out_flow=Decimal("10.00"), in_flow=None)
        with (
            patch(
                "ingestion_worker.embedding.service.repository.list_pending_transactions",
                return_value=[fake_transaction],
            ),
            patch("ingestion_worker.embedding.service.client.compute_embedding", return_value=None),
            patch("ingestion_worker.embedding.service.vector_store.upsert_embedding") as mock_upsert,
            patch("ingestion_worker.embedding.service.repository.mark_transaction_embedded") as mock_mark,
        ):
            processed = service.process_next_embedding_batch(db=None)

        assert processed == 0
        mock_upsert.assert_not_called()
        mock_mark.assert_not_called()

    def test_stops_early_when_vector_store_upsert_fails(self, db_session):
        """WR-26: the status flip only happens after a successful upsert -- a
        failed upsert must not mark the row completed."""
        txn = _make_transaction(db_session)

        with (
            patch("ingestion_worker.embedding.service.client.compute_embedding", return_value=[0.1]),
            patch("ingestion_worker.embedding.service.vector_store.upsert_embedding", return_value=False),
        ):
            processed = service.process_next_embedding_batch(db_session)

        assert processed == 0
        db_session.refresh(txn)
        assert txn.embedding_status == EmbeddingStatus.PENDING  # untouched -- safe to retry next cycle

    def test_no_pending_rows_is_a_no_op(self, db_session):
        with (
            patch("ingestion_worker.embedding.service.client.compute_embedding") as mock_compute,
        ):
            processed = service.process_next_embedding_batch(db_session)

        assert processed == 0
        mock_compute.assert_not_called()
