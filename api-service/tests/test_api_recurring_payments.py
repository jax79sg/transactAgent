import uuid
from datetime import date
from decimal import Decimal


def _make_category(db, name="Health"):
    from transactagent_db.models import Category

    category = Category(name=name, active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description="GYM MEMBERSHIP FEE", txn_date=None, category=None):
    from transactagent_db.models import BankStatement, CategorySource, Transaction

    category = category or _make_category(db)
    statement = BankStatement(drive_file_id="f1", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32])
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=txn_date or date.today(),
        description=description,
        out_flow=Decimal("80.00"),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_payment(db, **overrides):
    from transactagent_db.models import RecurringPayment, RecurringPaymentFrequency

    defaults = dict(
        name="Gym Membership", expected_amount=Decimal("80.00"), frequency=RecurringPaymentFrequency.MONTHLY, due_day=15
    )
    defaults.update(overrides)
    payment = RecurringPayment(**defaults)
    db.add(payment)
    db.flush()
    return payment


def _make_match(db, payment, txn, cycle_period, match_status):
    from transactagent_db.models import RecurringPaymentMatch

    match = RecurringPaymentMatch(
        recurring_payment_id=payment.id,
        transaction_id=txn.id,
        cycle_period=cycle_period,
        status=match_status,
        amount_at_match=Decimal("80.00"),
    )
    db.add(match)
    db.flush()
    return match


class TestRecurringPaymentsCrudApi:
    def test_requires_auth(self, client):
        response = client.get("/recurring-payments")
        assert response.status_code == 401

    def test_create_then_list(self, client, auth_headers):
        create_response = client.post(
            "/recurring-payments",
            json={"name": "Gym Membership", "expectedAmount": "80.00", "frequency": "monthly", "dueDay": 15},
            headers=auth_headers,
        )
        assert create_response.status_code == 201
        body = create_response.json()
        assert body["name"] == "Gym Membership"
        assert body["dueMonth"] is None

        list_response = client.get("/recurring-payments", headers=auth_headers)
        assert any(p["id"] == body["id"] for p in list_response.json())

    def test_create_annual_without_due_month_returns_400(self, client, auth_headers):
        response = client.post(
            "/recurring-payments",
            json={"name": "Car Insurance", "expectedAmount": "1200.00", "frequency": "annual", "dueDay": 21},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_recurring_payment"

    def test_update_and_delete(self, client, auth_headers, db_session):
        payment = _make_payment(db_session)

        update_response = client.put(
            f"/recurring-payments/{payment.id}",
            json={"name": "Gym Membership Plus", "expectedAmount": "90.00", "frequency": "monthly", "dueDay": 20},
            headers=auth_headers,
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Gym Membership Plus"

        delete_response = client.delete(f"/recurring-payments/{payment.id}", headers=auth_headers)
        assert delete_response.status_code == 204

    def test_update_unknown_returns_404(self, client, auth_headers):
        response = client.put(
            f"/recurring-payments/{uuid.uuid4()}",
            json={"name": "X", "expectedAmount": "1.00", "frequency": "monthly", "dueDay": 1},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestBulkImportApi:
    def test_partial_success_reported_per_row(self, client, auth_headers):
        response = client.post(
            "/recurring-payments/bulk-import",
            json={
                "rows": [
                    {"name": "Gym Membership", "amount": "80.00", "frequency": "monthly", "dueDay": "15"},
                    {"name": "Bad Row", "amount": "10.00", "frequency": "monthly", "dueDay": "99"},
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["created"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["row"] == 1

    def test_unparseable_amount_does_not_422_the_whole_request(self, client, auth_headers):
        """Regression test for a bug found via live verification: amount/dueMonth/dueDay
        used to be typed Decimal/int on the request schema, so one garbled value made
        FastAPI reject the entire batch with a 422 before AR-19's per-row isolation ever
        ran -- silently discarding every valid row in the same request."""
        response = client.post(
            "/recurring-payments/bulk-import",
            json={
                "rows": [
                    {"name": "Gym Membership", "amount": "80.00", "frequency": "monthly", "dueDay": "15"},
                    {"name": "Bad Row", "amount": "not-a-number", "frequency": "monthly", "dueDay": "1"},
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["created"]) == 1
        assert len(body["failed"]) == 1
        assert body["failed"][0]["row"] == 1


class TestMatchReviewApi:
    def test_approve_marks_paid_and_trusts_payment(self, client, auth_headers, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        match = _make_match(db_session, payment, txn, "2026-08", "pending")

        response = client.post(f"/recurring-payments/matches/{match.id}/approve", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    def test_reject_then_approve_returns_409(self, client, auth_headers, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        match = _make_match(db_session, payment, txn, "2026-08", "pending")

        first = client.post(f"/recurring-payments/matches/{match.id}/reject", headers=auth_headers)
        assert first.status_code == 200

        second = client.post(f"/recurring-payments/matches/{match.id}/approve", headers=auth_headers)
        assert second.status_code == 409
        assert second.json()["error"] == "match_not_pending"

    def test_list_pending_matches(self, client, auth_headers, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        _make_match(db_session, payment, txn, "2026-08", "pending")

        response = client.get("/recurring-payments/matches", headers=auth_headers)

        assert response.status_code == 200
        assert len(response.json()) == 1


class TestDetectionSuggestionApi:
    def _make_suggestion(self, db):
        from transactagent_db.models import DetectionSuggestion

        suggestion = DetectionSuggestion(
            description_pattern="STREAMING SERVICE", suggested_amount=Decimal("15.00"), occurrence_count=2
        )
        db.add(suggestion)
        db.flush()
        return suggestion

    def test_list_and_dismiss(self, client, auth_headers, db_session):
        suggestion = self._make_suggestion(db_session)

        list_response = client.get("/recurring-payments/detection-suggestions", headers=auth_headers)
        assert len(list_response.json()) == 1

        dismiss_response = client.post(
            f"/recurring-payments/detection-suggestions/{suggestion.id}/dismiss", headers=auth_headers
        )
        assert dismiss_response.status_code == 204

        after_response = client.get("/recurring-payments/detection-suggestions", headers=auth_headers)
        assert after_response.json() == []

    def test_add_creates_prefilled_payment(self, client, auth_headers, db_session):
        suggestion = self._make_suggestion(db_session)

        response = client.post(
            f"/recurring-payments/detection-suggestions/{suggestion.id}/add", json={}, headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["name"] == "STREAMING SERVICE"


class TestStatusSummaryApi:
    def test_requires_auth(self, client):
        response = client.get("/recurring-payments/status")
        assert response.status_code == 401

    def test_reflects_pending_matches(self, client, auth_headers, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session)
        _make_match(db_session, payment, txn, "2026-08", "pending")

        response = client.get("/recurring-payments/status", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["pendingMatchCount"] == 1
