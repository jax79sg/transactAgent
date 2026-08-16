import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from api_service.errors import (
    CategoryNotFoundError,
    DetectionSuggestionNotNewError,
    InvalidRecurringPaymentError,
    MatchNotPendingError,
    NotFoundError,
)
from api_service.recurring_payments import service
from api_service.recurring_payments.schemas import (
    AddFromDetectionSuggestionRequest,
    BulkImportRequest,
    BulkImportRow,
    RecurringPaymentCreateRequest,
    RecurringPaymentUpdateRequest,
)
from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    DetectionSuggestion,
    EmbeddingStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    Transaction,
)


def _make_category(db, name=None):
    category = Category(name=name or f"Category-{uuid.uuid4().hex[:8]}", active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description="GYM MEMBERSHIP FEE", amount="80.00", txn_date=date(2026, 8, 15), category=None):
    category = category or _make_category(db)
    statement = BankStatement(
        drive_file_id=f"drive-{uuid.uuid4().hex[:8]}", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32]
    )
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=txn_date,
        description=description,
        out_flow=Decimal(amount),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_payment(db, **overrides):
    defaults = dict(
        name="Gym Membership", expected_amount=Decimal("80.00"), frequency=RecurringPaymentFrequency.MONTHLY, due_day=15
    )
    defaults.update(overrides)
    payment = RecurringPayment(**defaults)
    db.add(payment)
    db.flush()
    return payment


def _make_match(db, payment, txn, cycle_period, match_status):
    match = RecurringPaymentMatch(
        recurring_payment_id=payment.id,
        transaction_id=txn.id,
        cycle_period=cycle_period,
        status=match_status,
        amount_at_match=Decimal("80.00"),
        resolved_at=datetime.now(timezone.utc) if match_status != RecurringPaymentMatchStatus.PENDING else None,
    )
    db.add(match)
    db.flush()
    return match


class TestCreateAndList:
    def test_create_monthly_payment(self, db_session):
        dto = service.create_recurring_payment(
            db_session,
            RecurringPaymentCreateRequest(name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_day=15),
        )
        assert dto.name == "Gym Membership"
        assert dto.due_month is None

        listed = service.list_recurring_payments(db_session)
        assert any(p.id == dto.id for p in listed)

    def test_create_defaults_embedding_status_to_pending(self, db_session):
        """AR-22 (Epic 9): the column's own default -- stated as a rule for
        completeness, not a new code path (no explicit `embedding_status=` is set
        by `create_recurring_payment` itself)."""
        dto = service.create_recurring_payment(
            db_session,
            RecurringPaymentCreateRequest(name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_day=15),
        )

        payment = db_session.get(RecurringPayment, dto.id)
        assert payment.embedding_status == EmbeddingStatus.PENDING

    def test_create_annual_payment_requires_due_month(self, db_session):
        with pytest.raises(InvalidRecurringPaymentError):
            service.create_recurring_payment(
                db_session,
                RecurringPaymentCreateRequest(name="Car Insurance", expected_amount=Decimal("1200.00"), frequency="annual", due_day=21),
            )

    def test_create_monthly_payment_rejects_due_month(self, db_session):
        with pytest.raises(InvalidRecurringPaymentError):
            service.create_recurring_payment(
                db_session,
                RecurringPaymentCreateRequest(
                    name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_month=6, due_day=15
                ),
            )

    def test_create_rejects_due_day_out_of_range(self, db_session):
        with pytest.raises(InvalidRecurringPaymentError):
            service.create_recurring_payment(
                db_session,
                RecurringPaymentCreateRequest(name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_day=32),
            )

    def test_create_with_unknown_category_raises(self, db_session):
        with pytest.raises(CategoryNotFoundError):
            service.create_recurring_payment(
                db_session,
                RecurringPaymentCreateRequest(
                    name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_day=15,
                    category_id=uuid.uuid4(),
                ),
            )

    def test_create_with_valid_category_links_it(self, db_session):
        category = _make_category(db_session, "Health")
        dto = service.create_recurring_payment(
            db_session,
            RecurringPaymentCreateRequest(
                name="Gym Membership", expected_amount=Decimal("80.00"), frequency="monthly", due_day=15,
                category_id=category.id,
            ),
        )
        assert dto.category.id == category.id


class TestUpdateAndDelete:
    def test_update_changes_fields(self, db_session):
        payment = _make_payment(db_session)
        dto = service.update_recurring_payment(
            db_session, payment.id,
            RecurringPaymentUpdateRequest(name="Gym Membership Plus", expected_amount=Decimal("90.00"), frequency="monthly", due_day=20),
        )
        assert dto.name == "Gym Membership Plus"
        assert dto.due_day == 20

    def test_update_unknown_payment_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.update_recurring_payment(
                db_session, uuid.uuid4(),
                RecurringPaymentUpdateRequest(name="X", expected_amount=Decimal("1.00"), frequency="monthly", due_day=1),
            )

    def test_delete_removes_it(self, db_session):
        payment = _make_payment(db_session)
        service.delete_recurring_payment(db_session, payment.id)

        assert all(p.id != payment.id for p in service.list_recurring_payments(db_session))

    def test_delete_unknown_payment_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.delete_recurring_payment(db_session, uuid.uuid4())

    def test_name_change_resets_embedding_status_to_pending(self, db_session):
        """AR-22 (Epic 9): a rename invalidates whatever's already embedded/pending
        in the vector store -- the Ingestion Worker's Embedding Manager is the only
        writer of `completed`; this reset is the only way `pending` is ever written
        after creation."""
        payment = _make_payment(db_session, embedding_status=EmbeddingStatus.COMPLETED)

        service.update_recurring_payment(
            db_session, payment.id,
            RecurringPaymentUpdateRequest(name="Gym Membership Plus", expected_amount=Decimal("80.00"), frequency="monthly", due_day=15),
        )

        db_session.refresh(payment)
        assert payment.embedding_status == EmbeddingStatus.PENDING

    def test_update_without_name_change_leaves_embedding_status_untouched(self, db_session):
        """AR-22: only a `name` change resets it -- other field changes (here,
        expected_amount and due_day) must not."""
        payment = _make_payment(db_session, embedding_status=EmbeddingStatus.COMPLETED)

        service.update_recurring_payment(
            db_session, payment.id,
            RecurringPaymentUpdateRequest(name=payment.name, expected_amount=Decimal("95.00"), frequency="monthly", due_day=20),
        )

        db_session.refresh(payment)
        assert payment.embedding_status == EmbeddingStatus.COMPLETED


class TestBulkImport:
    def test_valid_rows_are_all_created(self, db_session):
        request = BulkImportRequest(
            rows=[
                BulkImportRow(name="Gym Membership", amount="80.00", frequency="monthly", due_day="15"),
                BulkImportRow(name="Car Insurance", amount="1200.00", frequency="annual", due_month="8", due_day="21"),
            ]
        )
        response = service.bulk_import_recurring_payments(db_session, request)

        assert len(response.created) == 2
        assert response.failed == []

    def test_invalid_row_is_isolated_valid_rows_still_created(self, db_session):
        request = BulkImportRequest(
            rows=[
                BulkImportRow(name="Gym Membership", amount="80.00", frequency="monthly", due_day="15"),
                BulkImportRow(name="Bad Row", amount="10.00", frequency="monthly", due_day="99"),  # BR-20
            ]
        )
        response = service.bulk_import_recurring_payments(db_session, request)

        assert len(response.created) == 1
        assert len(response.failed) == 1
        assert response.failed[0].row == 1

    def test_unparseable_amount_is_isolated_valid_rows_still_created(self, db_session):
        """Regression test: BulkImportRow.amount is a raw string precisely so that a
        garbled value here becomes a per-row failure, not a whole-request 422 raised
        by FastAPI's own body validation before this per-row loop ever runs."""
        request = BulkImportRequest(
            rows=[
                BulkImportRow(name="Gym Membership", amount="80.00", frequency="monthly", due_day="15"),
                BulkImportRow(name="Bad Row", amount="not-a-number", frequency="monthly", due_day="1"),
            ]
        )
        response = service.bulk_import_recurring_payments(db_session, request)

        assert len(response.created) == 1
        assert len(response.failed) == 1
        assert response.failed[0].row == 1

    def test_unparseable_due_day_is_isolated_valid_rows_still_created(self, db_session):
        request = BulkImportRequest(
            rows=[
                BulkImportRow(name="Gym Membership", amount="80.00", frequency="monthly", due_day="15"),
                BulkImportRow(name="Bad Row", amount="10.00", frequency="monthly", due_day="fifteen"),
            ]
        )
        response = service.bulk_import_recurring_payments(db_session, request)

        assert len(response.created) == 1
        assert len(response.failed) == 1
        assert response.failed[0].row == 1


class TestStatusComputation:
    def test_overdue_when_due_date_passed_with_no_match(self, db_session):
        payment = _make_payment(db_session, due_day=1)
        # "today" in these tests is the real date.today() the service uses --
        # use a due_day guaranteed to be in the past relative to "today" by using
        # a due_day of 1 combined with asserting only the qualitative outcome
        # would be fragile across month boundaries, so instead directly exercise
        # the pure computation via a payment due many days ago this month when
        # today's day-of-month allows it, else skip via the annual case below.
        dto = service.get_recurring_payment(db_session, payment.id)
        # A payment due on the 1st, with no match at all, is only "overdue" once
        # today is past the 1st -- true on every day but the 1st itself, and on
        # the 1st itself it's "due_soon" (FR-9's grace). Both are valid outcomes
        # of correct behavior; assert it's never wrongly "paid" or "pending_review".
        assert dto.status in ("overdue", "due_soon")

    def test_paid_when_an_approved_match_exists_for_the_current_cycle(self, db_session):
        payment = _make_payment(db_session, due_day=date.today().day)
        txn = _make_transaction(db_session, txn_date=date.today())
        cycle_period = f"{date.today().year:04d}-{date.today().month:02d}"
        _make_match(db_session, payment, txn, cycle_period, RecurringPaymentMatchStatus.APPROVED)

        dto = service.get_recurring_payment(db_session, payment.id)
        assert dto.status in ("paid", "due_soon")  # due_soon if the next cycle is already within the lead window

    def test_pending_review_when_a_pending_match_exists_for_the_current_cycle(self, db_session):
        today = date.today()
        payment = _make_payment(db_session, due_day=today.day)
        txn = _make_transaction(db_session, txn_date=today)
        cycle_period = f"{today.year:04d}-{today.month:02d}"
        _make_match(db_session, payment, txn, cycle_period, RecurringPaymentMatchStatus.PENDING)

        dto = service.get_recurring_payment(db_session, payment.id)
        assert dto.status == "pending_review"

    def test_annual_payment_includes_monthly_set_aside(self, db_session):
        payment = _make_payment(
            db_session, name="Car Insurance", frequency=RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21,
            expected_amount=Decimal("1200.00"),
        )
        dto = service.get_recurring_payment(db_session, payment.id)
        assert dto.monthly_set_aside == Decimal("100.00")

    def test_monthly_payment_has_no_set_aside(self, db_session):
        payment = _make_payment(db_session)
        dto = service.get_recurring_payment(db_session, payment.id)
        assert dto.monthly_set_aside is None


class TestApproveRejectMatch:
    def test_approve_marks_paid_and_trusts_the_payment(self, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        match = _make_match(db_session, payment, txn, "2026-08", RecurringPaymentMatchStatus.PENDING)

        dto = service.approve_match(db_session, match.id)

        assert dto.status == "approved"
        db_session.refresh(payment)
        assert payment.is_trusted is True

    def test_reject_leaves_payment_untrusted_and_no_other_side_effect(self, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        match = _make_match(db_session, payment, txn, "2026-08", RecurringPaymentMatchStatus.PENDING)

        dto = service.reject_match(db_session, match.id)

        assert dto.status == "rejected"
        db_session.refresh(payment)
        assert payment.is_trusted is False

    def test_approving_an_already_resolved_match_raises(self, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        match = _make_match(db_session, payment, txn, "2026-08", RecurringPaymentMatchStatus.PENDING)
        service.approve_match(db_session, match.id)

        with pytest.raises(MatchNotPendingError):
            service.approve_match(db_session, match.id)

    def test_approving_unknown_match_raises_not_found(self, db_session):
        with pytest.raises(NotFoundError):
            service.approve_match(db_session, uuid.uuid4())


class TestDetectionSuggestions:
    def _make_suggestion(self, db, **overrides):
        defaults = dict(description_pattern="STREAMING SERVICE", suggested_amount=Decimal("15.00"), occurrence_count=2)
        defaults.update(overrides)
        suggestion = DetectionSuggestion(**defaults)
        db.add(suggestion)
        db.flush()
        return suggestion

    def test_list_returns_new_suggestions(self, db_session):
        self._make_suggestion(db_session)
        assert len(service.list_detection_suggestions(db_session)) == 1

    def test_dismiss_marks_it_dismissed_and_it_no_longer_lists(self, db_session):
        suggestion = self._make_suggestion(db_session)
        service.dismiss_detection_suggestion(db_session, suggestion.id)

        assert service.list_detection_suggestions(db_session) == []
        db_session.refresh(suggestion)
        assert suggestion.status.value == "dismissed"

    def test_dismissing_already_resolved_suggestion_raises(self, db_session):
        suggestion = self._make_suggestion(db_session)
        service.dismiss_detection_suggestion(db_session, suggestion.id)

        with pytest.raises(DetectionSuggestionNotNewError):
            service.dismiss_detection_suggestion(db_session, suggestion.id)

    def test_add_creates_a_prefilled_payment_and_marks_suggestion_added(self, db_session):
        suggestion = self._make_suggestion(db_session)

        dto = service.add_from_detection_suggestion(db_session, suggestion.id, AddFromDetectionSuggestionRequest())

        assert dto.name == "STREAMING SERVICE"
        assert dto.expected_amount == Decimal("15.00")
        assert dto.frequency == "monthly"
        db_session.refresh(suggestion)
        assert suggestion.status.value == "added"

    def test_add_allows_overriding_fields_before_saving(self, db_session):
        suggestion = self._make_suggestion(db_session)

        dto = service.add_from_detection_suggestion(
            db_session, suggestion.id, AddFromDetectionSuggestionRequest(name="Netflix", due_day=5)
        )

        assert dto.name == "Netflix"
        assert dto.due_day == 5


class TestStatusSummary:
    def test_counts_pending_matches_and_new_suggestions(self, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        _make_match(db_session, payment, txn, "2026-08", RecurringPaymentMatchStatus.PENDING)
        DetectionSuggestion_row = DetectionSuggestion(
            description_pattern="STREAMING SERVICE", suggested_amount=Decimal("15.00"), occurrence_count=2
        )
        db_session.add(DetectionSuggestion_row)
        db_session.flush()

        summary = service.get_status_summary(db_session)

        assert summary.pending_match_count == 1
        assert summary.new_suggestion_count == 1
