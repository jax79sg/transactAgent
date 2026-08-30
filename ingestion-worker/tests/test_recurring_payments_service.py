"""Integration-style tests for recurring_payments/service.py: real Postgres
(testcontainers), no external clients involved (this component is pure DB + pure
date/similarity math, unlike drive_client-dependent components).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    DetectionScanRun,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    Transaction,
)

from ingestion_worker.recurring_payments import service


def _make_category(db, name=None):
    category = Category(name=name or f"Category-{uuid.uuid4().hex[:8]}", active=True, is_reserved=False)
    db.add(category)
    db.flush()
    return category


def _make_transaction(db, description, amount, transaction_date, category=None):
    category = category or _make_category(db)
    statement = BankStatement(
        drive_file_id=f"drive-{uuid.uuid4().hex[:8]}", pdf_content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32]
    )
    db.add(statement)
    db.flush()
    txn = Transaction(
        bank_statement_id=statement.id,
        transaction_date=transaction_date,
        description=description,
        out_flow=Decimal(str(amount)),
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    db.add(txn)
    db.flush()
    return txn


def _make_payment(db, **overrides):
    defaults = {
        "name": "Gym Membership",
        "expected_amount": Decimal("80.00"),
        "frequency": RecurringPaymentFrequency.MONTHLY,
        "due_day": 15,
    }
    defaults.update(overrides)
    payment = RecurringPayment(**defaults)
    db.add(payment)
    db.flush()
    return payment


class TestMatchNewTransaction:
    def test_creates_pending_match_within_window_for_never_trusted_payment(self, db_session):
        payment = _make_payment(db_session)
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 16))

        service.match_new_transaction(db_session, txn)

        matches = db_session.query(RecurringPaymentMatch).filter_by(recurring_payment_id=payment.id).all()
        assert len(matches) == 1
        assert matches[0].status == RecurringPaymentMatchStatus.PENDING
        assert matches[0].cycle_period == "2026-08"

    def test_no_match_outside_due_date_window(self, db_session):
        _make_payment(db_session, due_day=1)
        # Default match window is 5 days; day 20 is nowhere near the 1st of any month.
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 20))

        service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).count() == 0

    def test_no_match_when_description_similarity_too_low(self, db_session):
        _make_payment(db_session, name="Gym Membership")
        txn = _make_transaction(db_session, "COMPLETELY UNRELATED MERCHANT XYZ", "80.00", date(2026, 8, 15))

        service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).count() == 0

    def test_no_duplicate_match_when_cycle_already_has_a_live_match(self, db_session):
        payment = _make_payment(db_session)
        first_txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 15))
        service.match_new_transaction(db_session, first_txn)
        assert db_session.query(RecurringPaymentMatch).count() == 1

        second_txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 16))
        service.match_new_transaction(db_session, second_txn)

        # Still just one match -- the cycle already has a live (pending) one.
        assert db_session.query(RecurringPaymentMatch).filter_by(recurring_payment_id=payment.id).count() == 1

    def test_auto_applies_for_trusted_payment_within_tolerance(self, db_session):
        _make_payment(db_session, is_trusted=True, expected_amount=Decimal("80.00"))
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "81.00", date(2026, 8, 15))

        service.match_new_transaction(db_session, txn)

        match = db_session.query(RecurringPaymentMatch).one()
        assert match.status == RecurringPaymentMatchStatus.AUTO_APPLIED

    def test_falls_back_to_pending_when_trusted_payment_amount_drifts_too_far(self, db_session):
        """FR-7's explicit edge case: trust doesn't mean unconditional auto-apply."""
        _make_payment(db_session, is_trusted=True, expected_amount=Decimal("80.00"))
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "400.00", date(2026, 8, 15))

        service.match_new_transaction(db_session, txn)

        match = db_session.query(RecurringPaymentMatch).one()
        assert match.status == RecurringPaymentMatchStatus.PENDING

    def test_matches_annual_payment(self, db_session):
        _make_payment(db_session, name="Car Insurance", frequency=RecurringPaymentFrequency.ANNUAL, due_month=8, due_day=21)
        txn = _make_transaction(db_session, "CAR INSURANCE", "1200.00", date(2026, 8, 21))

        service.match_new_transaction(db_session, txn)

        match = db_session.query(RecurringPaymentMatch).one()
        assert match.cycle_period == "2026"


class TestMatchNewTransactionEmbeddingFirst:
    """WR-21/22 (Epic 9): embedding-based candidate search against the
    `recurring_payment_names` vector-store collection, tried before the fuzzy-text
    check. compute_embedding/query_nearest_neighbors are mocked -- a real Qdrant
    instance is exercised at Build and Test, not here."""

    def test_embedding_match_found_even_when_fuzzy_text_would_reject_it(self, db_session):
        payment = _make_payment(db_session, name="Gym Membership")
        # Deliberately not a fuzzy match -- the mocked embedding path is the only
        # thing that can find this one, proving embedding is actually consulted.
        txn = _make_transaction(db_session, "COMPLETELY UNRELATED WORDING", "80.00", date(2026, 8, 15))

        with (
            patch("ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.recurring_payments.service.vector_store.query_nearest_neighbors",
                return_value=[(str(payment.id), 0.99)],
            ),
        ):
            service.match_new_transaction(db_session, txn)

        matches = db_session.query(RecurringPaymentMatch).filter_by(recurring_payment_id=payment.id).all()
        assert len(matches) == 1

    def test_falls_back_to_fuzzy_text_when_embedding_unavailable(self, db_session):
        _make_payment(db_session, name="Gym Membership")
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 15))

        with patch(
            "ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=None
        ):
            service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).count() == 1  # fuzzy-text still finds it

    def test_embedding_finding_nothing_falls_back_to_fuzzy_for_every_payment(self, db_session):
        """WR-21 step 4 is a whole-operation fallback, not per-payment: if the
        embedding search runs successfully but clears zero candidates, every
        payment still gets its fuzzy-text chance."""
        _make_payment(db_session, name="Gym Membership")
        txn = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 8, 15))

        with (
            patch("ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.recurring_payments.service.vector_store.query_nearest_neighbors", return_value=[]
            ),
        ):
            service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).count() == 1

    def test_llm_agreement_boost_lifts_a_below_threshold_candidate(self, db_session):
        """WR-30 (Matching Precision Refinement): a raw score just below the
        threshold is lifted above it when the transaction's own LLM classification
        (already persisted, WR-28) agrees with the candidate payment's category."""
        subscriptions = _make_category(db_session, "Subscriptions")
        payment = _make_payment(db_session, name="Gym Membership", category_id=subscriptions.id)
        txn = _make_transaction(db_session, "COMPLETELY UNRELATED WORDING", "80.00", date(2026, 8, 15))
        txn.llm_suggested_category_id = subscriptions.id
        db_session.flush()

        # Default embedding_similarity_threshold is 0.92; 0.90 alone doesn't clear
        # it, but 0.90 + the default 0.05 boost = 0.95 does.
        with (
            patch("ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.recurring_payments.service.vector_store.query_nearest_neighbors",
                return_value=[(str(payment.id), 0.90)],
            ),
        ):
            service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).filter_by(recurring_payment_id=payment.id).count() == 1

    def test_no_boost_when_llm_category_disagrees_with_payment_category(self, db_session):
        subscriptions = _make_category(db_session, "Subscriptions")
        groceries = _make_category(db_session, "Groceries")
        payment = _make_payment(db_session, name="Gym Membership", category_id=subscriptions.id)
        txn = _make_transaction(db_session, "COMPLETELY UNRELATED WORDING", "80.00", date(2026, 8, 15))
        txn.llm_suggested_category_id = groceries.id
        db_session.flush()

        with (
            patch("ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=[0.1]),
            patch(
                "ingestion_worker.recurring_payments.service.vector_store.query_nearest_neighbors",
                return_value=[(str(payment.id), 0.80)],
            ),
        ):
            service.match_new_transaction(db_session, txn)

        assert db_session.query(RecurringPaymentMatch).filter_by(recurring_payment_id=payment.id).count() == 0


class TestIsDetectionScanDueNow:
    def test_due_when_no_prior_scan(self, db_session):
        assert service.is_detection_scan_due_now(db_session) is True

    def test_not_due_when_recent_scan_exists(self, db_session):
        db_session.add(DetectionScanRun(ran_at=datetime.now(UTC)))
        db_session.flush()

        assert service.is_detection_scan_due_now(db_session) is False

    def test_due_when_last_scan_older_than_interval(self, db_session):
        stale = datetime.now(UTC) - timedelta(hours=48)
        db_session.add(DetectionScanRun(ran_at=stale))
        db_session.flush()

        assert service.is_detection_scan_due_now(db_session) is True


class TestRunDetectionScan:
    def test_creates_suggestion_for_a_repeating_monthly_pattern(self, db_session):
        category = _make_category(db_session, "Subscriptions")
        _make_transaction(db_session, "STREAMING SERVICE", "15.00", date(2026, 6, 5), category=category)
        _make_transaction(db_session, "STREAMING SERVICE", "15.00", date(2026, 7, 5), category=category)

        service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        suggestions = db_session.query(DetectionSuggestion).all()
        assert len(suggestions) == 1
        assert suggestions[0].description_pattern == "STREAMING SERVICE"
        assert suggestions[0].occurrence_count == 2
        assert suggestions[0].suggested_category_id == category.id

    def test_ignores_pattern_with_too_few_occurrences(self, db_session):
        _make_transaction(db_session, "ONE OFF PURCHASE", "50.00", date(2026, 7, 5))

        service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        assert db_session.query(DetectionSuggestion).count() == 0

    def test_ignores_transactions_already_matched_to_an_existing_payment(self, db_session):
        payment = _make_payment(db_session, name="Gym Membership")
        txn1 = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 6, 15))
        txn2 = _make_transaction(db_session, "GYM MEMBERSHIP FEE", "80.00", date(2026, 7, 15))
        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn1.id,
                cycle_period="2026-06",
                status=RecurringPaymentMatchStatus.APPROVED,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn2.id,
                cycle_period="2026-07",
                status=RecurringPaymentMatchStatus.APPROVED,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.flush()

        service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        assert db_session.query(DetectionSuggestion).count() == 0

    def test_does_not_duplicate_an_existing_suggestion(self, db_session):
        from transactagent_db.models import DetectionSuggestion

        db_session.add(
            DetectionSuggestion(
                description_pattern="STREAMING SERVICE", suggested_amount=Decimal("15.00"), occurrence_count=2
            )
        )
        db_session.flush()
        _make_transaction(db_session, "STREAMING SERVICE", "15.00", date(2026, 6, 5))
        _make_transaction(db_session, "STREAMING SERVICE", "15.00", date(2026, 7, 5))

        service.run_detection_scan(db_session)

        assert db_session.query(DetectionSuggestion).count() == 1  # unchanged

    def test_records_a_scan_run_even_when_nothing_is_found(self, db_session):
        service.run_detection_scan(db_session)

        assert db_session.query(DetectionScanRun).count() == 1

    def test_creates_suggestion_for_a_repeating_annual_pattern(self, db_session):
        """Issue #15: detection previously could only ever find monthly-cadence
        patterns (FR-12) -- an annual renewal, paid once a year, was structurally
        undetectable. suggested_due_month/suggested_due_day should default to the
        most recent occurrence's actual calendar day, not today's."""
        category = _make_category(db_session, "Insurance")
        _make_transaction(db_session, "ANNUAL INSURANCE RENEWAL", "500.00", date(2025, 3, 20), category=category)
        _make_transaction(db_session, "ANNUAL INSURANCE RENEWAL", "500.00", date(2026, 3, 22), category=category)

        service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        suggestions = db_session.query(DetectionSuggestion).all()
        assert len(suggestions) == 1
        assert suggestions[0].detected_frequency == RecurringPaymentFrequency.ANNUAL
        assert suggestions[0].suggested_due_month == 3
        assert suggestions[0].suggested_due_day == 22

    def test_daily_pattern_is_never_suggested_even_with_many_occurrences(self, db_session):
        """The explicit requirement (issue #15): a daily-cadence pattern is almost
        certainly routine purchases (e.g. meals), not a bill, and must never be
        recommended -- exercised through the real scan, not just _detect_cadence
        directly, so a future change to run_detection_scan's own filtering can't
        silently reintroduce this."""
        category = _make_category(db_session, "Dining")
        for day in range(1, 11):
            _make_transaction(db_session, "COFFEE SHOP", "5.00", date(2026, 6, day), category=category)

        service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        assert db_session.query(DetectionSuggestion).count() == 0


class TestRunDetectionScanEmbeddingMerge:
    """WR-22 (Epic 9, corrected from the original Application Design addendum --
    this scan's own grouping mechanism is exact-normalized-description matching,
    not find_best_match; embedding search ADDITIONALLY merges two distinct groups
    whose representative transactions are similar, catching paraphrased text the
    plain normalized-string match alone would miss."""

    def test_merges_two_differently_worded_groups_when_embeddings_are_similar(self, db_session):
        category = _make_category(db_session, "Subscriptions")
        # Two DIFFERENT normalized-description keys ("NETFLIX.COM" vs "NETFLIX SG
        # PTE") -- would never merge under the plain exact-match grouping alone.
        _make_transaction(db_session, "NETFLIX.COM", "15.00", date(2026, 6, 5), category=category)
        _make_transaction(db_session, "NETFLIX SG PTE", "15.00", date(2026, 7, 5), category=category)

        # Same vector for every call -- makes every representative "identical" by
        # cosine similarity, simulating the embedding model recognizing these as
        # the same merchant.
        with patch(
            "ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=[0.1, 0.2]
        ):
            service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        suggestions = db_session.query(DetectionSuggestion).all()
        assert len(suggestions) == 1
        assert suggestions[0].occurrence_count == 2  # both transactions counted as one merged pattern

    def test_does_not_merge_when_embedding_is_unavailable(self, db_session):
        """Falls back to exactly today's behavior: two differently-worded groups
        stay separate, neither reaching the occurrence-count minimum alone."""
        category = _make_category(db_session, "Subscriptions")
        _make_transaction(db_session, "NETFLIX.COM", "15.00", date(2026, 6, 5), category=category)
        _make_transaction(db_session, "NETFLIX SG PTE", "15.00", date(2026, 7, 5), category=category)

        with patch(
            "ingestion_worker.recurring_payments.service.embedding_client.compute_embedding", return_value=None
        ):
            service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        assert db_session.query(DetectionSuggestion).count() == 0  # each group alone has only 1 occurrence

    def test_does_not_merge_when_below_similarity_threshold(self, db_session):
        category = _make_category(db_session, "Subscriptions")
        _make_transaction(db_session, "NETFLIX.COM", "15.00", date(2026, 6, 5), category=category)
        _make_transaction(db_session, "SPOTIFY PREMIUM", "15.00", date(2026, 7, 5), category=category)

        # Keyed by the WR-29 price-bucketed text (both $15.00 -> "$10 to $20") plus
        # the WR-36 direction token, not the bare description alone.
        vectors = {
            "NETFLIX.COM | $10 to $20 | outflow": [1.0, 0.0],
            "SPOTIFY PREMIUM | $10 to $20 | outflow": [0.0, 1.0],
        }  # orthogonal -> cosine 0.0

        with patch(
            "ingestion_worker.recurring_payments.service.embedding_client.compute_embedding",
            side_effect=lambda text: vectors[text],
        ):
            service.run_detection_scan(db_session)

        from transactagent_db.models import DetectionSuggestion

        assert db_session.query(DetectionSuggestion).count() == 0  # correctly stayed separate


class TestNormalizeDescription:
    def test_strips_trailing_reference_number(self):
        assert service._normalize_description("NTUC FAIRPRICE #1000") == "NTUC FAIRPRICE"

    def test_leaves_description_without_reference_number_unchanged(self):
        assert service._normalize_description("MCDONALDS") == "MCDONALDS"

    def test_uppercases(self):
        assert service._normalize_description("Netflix.com") == "NETFLIX.COM"


class TestHasMonthlyCadence:
    def test_two_occurrences_thirty_days_apart_is_monthly_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 7, 5))

        assert service._has_monthly_cadence([txn1, txn2]) is True

    def test_two_occurrences_two_days_apart_is_not_monthly_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 7))

        assert service._has_monthly_cadence([txn1, txn2]) is False

    def test_single_occurrence_is_never_a_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))

        assert service._has_monthly_cadence([txn1]) is False


class TestHasAnnualCadence:
    def test_two_occurrences_365_days_apart_is_annual_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2025, 1, 15))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 1, 15))

        assert service._has_annual_cadence([txn1, txn2]) is True

    def test_thirty_day_gap_is_not_annual_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 7, 5))

        assert service._has_annual_cadence([txn1, txn2]) is False


class TestDetectCadence:
    """Issue #15: _detect_cadence is the single entry point run_detection_scan
    actually calls -- these prove monthly/annual are both reachable through it, and
    that the explicit requirement ("don't recommend daily-cadence payments -- those
    are probably meal payments") holds regardless of which cadence window a gap is
    checked against."""

    def test_monthly_gap_resolves_to_monthly(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 7, 5))

        assert service._detect_cadence([txn1, txn2]) == RecurringPaymentFrequency.MONTHLY

    def test_annual_gap_resolves_to_annual(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2025, 1, 15))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 1, 15))

        assert service._detect_cadence([txn1, txn2]) == RecurringPaymentFrequency.ANNUAL

    def test_daily_gap_is_never_a_recurring_pattern(self, db_session):
        """The explicit requirement: a daily-cadence cluster (almost certainly
        routine purchases like meals, not a bill) must never be suggested, no
        matter how many occurrences pile up -- neither the monthly nor the annual
        window can ever match a ~1-day gap."""
        txns = [_make_transaction(db_session, "COFFEE SHOP", "5.00", date(2026, 6, day)) for day in range(1, 11)]

        assert service._detect_cadence(txns) is None

    def test_sporadic_gap_matching_neither_window_is_not_a_cadence(self, db_session):
        txn1 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 5))
        txn2 = _make_transaction(db_session, "X", "10.00", date(2026, 6, 12))  # 7 days -- below both windows

        assert service._detect_cadence([txn1, txn2]) is None
