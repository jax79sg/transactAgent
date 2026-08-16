"""Example-based tests verifying the schema enforces its documented business rules.

PBT is not applied to this unit (see database-code-generation-plan.md — no pure
transformation functions exist here; this unit is declarative schema/constraints only).
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from transactagent_db.models import (
    BackupRun,
    BackupRunFailureCategory,
    BackupRunOutcome,
    BankStatement,
    Category,
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    CategorySource,
    DetectionScanRun,
    DetectionSuggestion,
    DetectionSuggestionStatus,
    FxRateCache,
    IngestionRunFile,
    IngestionRunFileOutcome,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
)


def _make_category(session, name="Groceries", active=True, is_reserved=False):
    category = Category(name=name, active=active, is_reserved=is_reserved)
    session.add(category)
    session.flush()
    return category


def _make_bank_statement(session, pdf_content_hash="a" * 64):
    statement = BankStatement(drive_file_id="drive-file-1", pdf_content_hash=pdf_content_hash)
    session.add(statement)
    session.flush()
    return statement


def _base_transaction_kwargs(session, **overrides):
    category = overrides.pop("category", None) or _make_category(session)
    statement = overrides.pop("bank_statement", None) or _make_bank_statement(session)
    kwargs = dict(
        bank_statement_id=statement.id,
        transaction_date=date(2026, 1, 15),
        description="NTUC FAIRPRICE",
        currency="SGD",
        bank_name="DBS",
        category_id=category.id,
        category_source=CategorySource.SIMILARITY,
    )
    kwargs.update(overrides)
    return kwargs


class TestExactlyOneFlowDirection:
    """BR-2: exactly one of out_flow / in_flow must be a positive, non-null value."""

    def test_out_flow_only_is_valid(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("25.50"), in_flow=None))
        db_session.add(txn)
        db_session.flush()  # should not raise

    def test_in_flow_only_is_valid(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=None, in_flow=Decimal("1000.00")))
        db_session.add(txn)
        db_session.flush()  # should not raise

    def test_both_null_is_rejected(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=None, in_flow=None))
        db_session.add(txn)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_both_set_is_rejected(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(
            **_base_transaction_kwargs(
                db_session, out_flow=Decimal("10.00"), in_flow=Decimal("10.00")
            )
        )
        db_session.add(txn)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_negative_out_flow_is_rejected(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("-5.00"), in_flow=None))
        db_session.add(txn)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestStatementHashUniqueness:
    """BR-3: bank_statements.pdf_content_hash must be unique."""

    def test_duplicate_hash_is_rejected(self, db_session):
        _make_bank_statement(db_session, pdf_content_hash="b" * 64)
        db_session.flush()
        duplicate = BankStatement(drive_file_id="drive-file-2", pdf_content_hash="b" * 64)
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestCategoryNameUniqueness:
    """BR-4: categories.name must be unique across all rows (active and inactive)."""

    def test_duplicate_name_is_rejected(self, db_session):
        _make_category(db_session, name="Dining")
        db_session.flush()
        duplicate = Category(name="Dining", active=False)
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestFxRateCacheUniqueness:
    """BR-7: (from_currency, to_currency, rate_date) must be unique."""

    def test_duplicate_pair_and_date_is_rejected(self, db_session):
        db_session.add(
            FxRateCache(from_currency="USD", to_currency="SGD", rate_date=date(2026, 1, 15), rate=Decimal("1.35"))
        )
        db_session.flush()
        duplicate = FxRateCache(
            from_currency="USD", to_currency="SGD", rate_date=date(2026, 1, 15), rate=Decimal("1.36")
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_different_date_is_allowed(self, db_session):
        db_session.add(
            FxRateCache(from_currency="EUR", to_currency="SGD", rate_date=date(2026, 1, 15), rate=Decimal("1.45"))
        )
        db_session.flush()
        different_date = FxRateCache(
            from_currency="EUR", to_currency="SGD", rate_date=date(2026, 1, 16), rate=Decimal("1.46")
        )
        db_session.add(different_date)
        db_session.flush()  # should not raise


class TestFailedFileRequiresReason:
    """BR-9: an ingestion_run_file with outcome='failed' must have a non-null failure_reason."""

    def _make_run(self, session):
        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username="account_owner", password_hash="hashed")
        session.add(user)
        session.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        session.add(run)
        session.flush()
        return run

    def test_failed_without_reason_is_rejected(self, db_session):
        run = self._make_run(db_session)
        run_file = IngestionRunFile(
            ingestion_run_id=run.id,
            drive_file_id="drive-file-3",
            drive_file_name="statement.pdf",
            outcome=IngestionRunFileOutcome.FAILED,
            failure_reason=None,
        )
        db_session.add(run_file)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_failed_with_reason_is_valid(self, db_session):
        run = self._make_run(db_session)
        run_file = IngestionRunFile(
            ingestion_run_id=run.id,
            drive_file_id="drive-file-4",
            drive_file_name="statement.pdf",
            outcome=IngestionRunFileOutcome.FAILED,
            failure_reason="OCR unreadable",
        )
        db_session.add(run_file)
        db_session.flush()  # should not raise

    def test_processed_without_reason_is_valid(self, db_session):
        run = self._make_run(db_session)
        run_file = IngestionRunFile(
            ingestion_run_id=run.id,
            drive_file_id="drive-file-5",
            drive_file_name="statement.pdf",
            outcome=IngestionRunFileOutcome.PROCESSED,
            failure_reason=None,
        )
        db_session.add(run_file)
        db_session.flush()  # should not raise


class TestIngestionRunCancellation:
    """User-initiated cancellation (2026-08-05): cancel_requested_at is written only
    by the API, status=CANCELLED only by the worker -- see aidlc-docs/audit.md."""

    def test_cancel_requested_at_defaults_to_null(self, db_session):
        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username="account_owner", password_hash="hashed")
        db_session.add(user)
        db_session.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        db_session.add(run)
        db_session.flush()

        assert run.cancel_requested_at is None

    def test_cancelled_run_with_requested_at_is_valid(self, db_session):
        from datetime import datetime, timezone

        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username="account_owner", password_hash="hashed")
        db_session.add(user)
        db_session.flush()
        requested_at = datetime.now(timezone.utc)
        run = IngestionRun(
            triggered_by_user_id=user.id,
            status=IngestionRunStatus.CANCELLED,
            cancel_requested_at=requested_at,
            completed_at=requested_at,
        )
        db_session.add(run)
        db_session.flush()  # should not raise

        assert run.status == IngestionRunStatus.CANCELLED


class TestIngestionRunLog:
    """Live worker-log-tail feature: log lines belong to a run and get a
    monotonically-increasing id usable as a polling cursor."""

    def _make_run(self, session):
        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username="account_owner", password_hash="hashed")
        session.add(user)
        session.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.RUNNING)
        session.add(run)
        session.flush()
        return run

    def test_log_lines_get_increasing_ids_in_insert_order(self, db_session):
        from transactagent_db.models import IngestionRunLog

        run = self._make_run(db_session)
        first = IngestionRunLog(
            ingestion_run_id=run.id, level="INFO", logger_name="ingestion_worker.orchestrator.pipeline",
            message="Starting run",
        )
        db_session.add(first)
        db_session.flush()
        second = IngestionRunLog(
            ingestion_run_id=run.id, level="INFO", logger_name="ingestion_worker.orchestrator.pipeline",
            message="Downloading statement.pdf",
        )
        db_session.add(second)
        db_session.flush()

        assert second.id > first.id


class TestRecategorizationProposal:
    """Epic 6 (Recategorization Review Panel).

    BR-14 (at most one 'pending' proposal per candidate+job pair) is enforced by a raw-SQL
    partial unique index applied via Alembic (migrations/versions/0004_recategorization_proposals.py),
    not by anything `Base.metadata.create_all()` can create -- this file's fixtures build the
    schema via `create_all()` directly (see conftest.py), bypassing Alembic entirely. This is
    the same reason BR-10 (single active ingestion run, same raw-SQL-partial-index pattern) has
    no unit test in this file either -- both are verified at the Alembic-migration/integration
    level instead, not here. Tests below cover what IS testable through the ORM at this layer:
    basic model shape, relationships, and the two legitimate status-writing paths.
    """

    def _make_unrelated_transaction(self, session, description):
        """A fully independent transaction (its own category + bank statement, both
        with unique identifiers) so repeated calls within one test never collide on
        BR-4 (category name) or BR-3 (statement hash) uniqueness."""
        import uuid as uuid_module

        from transactagent_db.models import Transaction

        suffix = uuid_module.uuid4().hex
        category = _make_category(session, name=f"Placeholder {suffix[:8]}")
        statement = _make_bank_statement(session, pdf_content_hash=suffix.ljust(64, "0"))
        txn = Transaction(
            **_base_transaction_kwargs(
                session,
                description=description,
                out_flow=Decimal("18.00"),
                in_flow=None,
                category=category,
                bank_statement=statement,
            )
        )
        session.add(txn)
        session.flush()
        return txn

    def _make_job(self, session):
        source_txn = self._make_unrelated_transaction(session, description="AMAZON SG")
        job = RecategorizationJob(source_transaction_id=source_txn.id)
        session.add(job)
        session.flush()
        return job

    def _make_candidate(self, session, description="AMAZON WEB SVCS"):
        return self._make_unrelated_transaction(session, description=description)

    def test_pending_proposal_links_to_job_candidate_and_category(self, db_session):
        job = self._make_job(db_session)
        candidate = self._make_candidate(db_session)
        category = _make_category(db_session, name="Shopping")

        proposal = RecategorizationProposal(
            recategorization_job_id=job.id,
            candidate_transaction_id=candidate.id,
            proposed_category_id=category.id,
            match_score=Decimal("91.50"),
            source_bucket=RecategorizationProposalSourceBucket.UNSURE,
            status=RecategorizationProposalStatus.PENDING,
        )
        db_session.add(proposal)
        db_session.flush()
        db_session.refresh(job)
        db_session.refresh(candidate)
        db_session.refresh(category)

        assert proposal.recategorization_job_id == job.id
        assert proposal.status == RecategorizationProposalStatus.PENDING
        assert proposal.resolved_at is None
        assert proposal in job.proposals
        assert proposal in candidate.recategorization_proposals
        assert proposal in category.proposed_in_recategorization_proposals

    def test_categorized_bucket_proposal_is_valid(self, db_session):
        """US-6.3: a match against an already-categorized transaction is a legitimate
        pending proposal too, not just UNSURE-bucket matches."""
        job = self._make_job(db_session)
        candidate = self._make_candidate(db_session)
        category = _make_category(db_session, name="Household")

        proposal = RecategorizationProposal(
            recategorization_job_id=job.id,
            candidate_transaction_id=candidate.id,
            proposed_category_id=category.id,
            match_score=Decimal("99.90"),
            source_bucket=RecategorizationProposalSourceBucket.CATEGORIZED,
            status=RecategorizationProposalStatus.PENDING,
        )
        db_session.add(proposal)
        db_session.flush()  # should not raise -- even a near-perfect score stays pending for this bucket (US-6.3)

    def test_auto_applied_proposal_is_valid(self, db_session):
        """The auto-apply path (US-6.2) records a proposal directly as auto_applied,
        never passing through pending."""
        job = self._make_job(db_session)
        candidate = self._make_candidate(db_session, description="STARBUCKS #4521")
        category = _make_category(db_session, name="Dining")

        proposal = RecategorizationProposal(
            recategorization_job_id=job.id,
            candidate_transaction_id=candidate.id,
            proposed_category_id=category.id,
            match_score=Decimal("98.20"),
            source_bucket=RecategorizationProposalSourceBucket.UNSURE,
            status=RecategorizationProposalStatus.AUTO_APPLIED,
        )
        db_session.add(proposal)
        db_session.flush()  # should not raise


class TestBackupRun:
    """Epic 7 (Nightly Transaction Backup).

    BR-17 (one attempt per calendar day) and BR-18 (failure_category consistency)
    are both standing constraints (a standard unique constraint and a CHECK
    constraint respectively) created by Base.metadata.create_all() directly, unlike
    BR-10/BR-14's raw-SQL partial indexes -- so both are fully testable at this
    layer, no integration-level gap.
    """

    def _now(self):
        return datetime.now(timezone.utc)

    def test_successful_backup_run_is_valid(self, db_session):
        run = BackupRun(
            backup_date=date(2026, 8, 8),
            started_at=self._now(),
            completed_at=self._now(),
            outcome=BackupRunOutcome.SUCCESS,
            failure_category=None,
            transaction_count=2174,
            backup_filename="transactions-backup-20260808T020000Z.csv",
        )
        db_session.add(run)
        db_session.flush()  # should not raise

        assert run.outcome == BackupRunOutcome.SUCCESS
        assert run.failure_category is None

    def test_failed_backup_run_is_valid_with_failure_category(self, db_session):
        run = BackupRun(
            backup_date=date(2026, 8, 8),
            started_at=self._now(),
            completed_at=self._now(),
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.DRIVE_CONNECTIVITY,
        )
        db_session.add(run)
        db_session.flush()  # should not raise

    def test_failed_backup_run_without_failure_category_is_rejected(self, db_session):
        """BR-18: outcome='failed' requires a non-null failure_category."""
        run = BackupRun(
            backup_date=date(2026, 8, 8),
            started_at=self._now(),
            completed_at=self._now(),
            outcome=BackupRunOutcome.FAILED,
            failure_category=None,
        )
        db_session.add(run)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_successful_backup_run_with_failure_category_is_rejected(self, db_session):
        """BR-18: outcome='success' requires a null failure_category."""
        run = BackupRun(
            backup_date=date(2026, 8, 8),
            started_at=self._now(),
            completed_at=self._now(),
            outcome=BackupRunOutcome.SUCCESS,
            failure_category=BackupRunFailureCategory.OTHER,
        )
        db_session.add(run)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_duplicate_backup_date_is_rejected(self, db_session):
        """BR-17: at most one BackupRun row per calendar backup_date."""
        db_session.add(
            BackupRun(
                backup_date=date(2026, 8, 8),
                started_at=self._now(),
                completed_at=self._now(),
                outcome=BackupRunOutcome.SUCCESS,
                transaction_count=100,
                backup_filename="transactions-backup-20260808T020000Z.csv",
            )
        )
        db_session.flush()

        duplicate = BackupRun(
            backup_date=date(2026, 8, 8),
            started_at=self._now(),
            completed_at=self._now(),
            outcome=BackupRunOutcome.FAILED,
            failure_category=BackupRunFailureCategory.OTHER,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_different_backup_dates_are_both_valid(self, db_session):
        db_session.add(
            BackupRun(
                backup_date=date(2026, 8, 7),
                started_at=self._now(),
                completed_at=self._now(),
                outcome=BackupRunOutcome.SUCCESS,
                transaction_count=99,
                backup_filename="transactions-backup-20260807T020000Z.csv",
            )
        )
        db_session.add(
            BackupRun(
                backup_date=date(2026, 8, 8),
                started_at=self._now(),
                completed_at=self._now(),
                outcome=BackupRunOutcome.SUCCESS,
                transaction_count=100,
                backup_filename="transactions-backup-20260808T020000Z.csv",
            )
        )
        db_session.flush()  # should not raise


class TestRecurringPayment:
    """Epic 8 (Recurring Payments). BR-19 (annual requires due_month, monthly must
    not have one) and BR-20 (due_day 1-31) are both standing CHECK constraints,
    fully testable at this layer."""

    def test_monthly_payment_without_due_month_is_valid(self, db_session):
        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_month=None,
            due_day=15,
        )
        db_session.add(payment)
        db_session.flush()  # should not raise

        assert payment.is_trusted is False

    def test_annual_payment_with_due_month_is_valid(self, db_session):
        payment = RecurringPayment(
            name="Car Insurance",
            expected_amount=Decimal("1200.00"),
            frequency=RecurringPaymentFrequency.ANNUAL,
            due_month=8,
            due_day=21,
        )
        db_session.add(payment)
        db_session.flush()  # should not raise

    def test_annual_payment_without_due_month_is_rejected(self, db_session):
        """BR-19."""
        payment = RecurringPayment(
            name="Car Insurance",
            expected_amount=Decimal("1200.00"),
            frequency=RecurringPaymentFrequency.ANNUAL,
            due_month=None,
            due_day=21,
        )
        db_session.add(payment)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_monthly_payment_with_due_month_is_rejected(self, db_session):
        """BR-19."""
        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_month=6,
            due_day=15,
        )
        db_session.add(payment)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_due_day_zero_is_rejected(self, db_session):
        """BR-20."""
        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=0,
        )
        db_session.add(payment)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_due_day_32_is_rejected(self, db_session):
        """BR-20."""
        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=32,
        )
        db_session.add(payment)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_optional_category_link(self, db_session):
        category = _make_category(db_session, name="Subscriptions")
        payment = RecurringPayment(
            name="Streaming Service",
            expected_amount=Decimal("15.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=1,
            category_id=category.id,
        )
        db_session.add(payment)
        db_session.flush()
        db_session.refresh(category)

        assert payment in category.recurring_payments

    def test_category_link_is_optional(self, db_session):
        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=15,
            category_id=None,
        )
        db_session.add(payment)
        db_session.flush()  # should not raise


class TestRecurringPaymentEmbeddingStatus:
    """Epic 9 (Local Embedding-Based Semantic Similarity), BR-25 -- added
    retroactively during Ingestion Worker Service Functional Design. Same one-way
    pending -> completed transition as TestTransactionEmbeddingStatus (BR-24), but
    this field can also be reset back to pending by the API Service on a name
    change (not exercised at this layer -- that's a Unit 2 application-layer
    concern; this only verifies the column/default itself)."""

    def test_new_payment_defaults_to_pending(self, db_session):
        from transactagent_db.models import EmbeddingStatus

        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=15,
        )
        db_session.add(payment)
        db_session.flush()
        db_session.refresh(payment)

        assert payment.embedding_status == EmbeddingStatus.PENDING

    def test_can_transition_to_completed(self, db_session):
        from transactagent_db.models import EmbeddingStatus

        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=15,
        )
        db_session.add(payment)
        db_session.flush()

        payment.embedding_status = EmbeddingStatus.COMPLETED
        db_session.flush()
        db_session.refresh(payment)

        assert payment.embedding_status == EmbeddingStatus.COMPLETED

    def test_can_reset_to_pending_after_rename(self, db_session):
        """Mirrors what the API Service's Recurring Payments Component does on a
        name-changing update (BR-25) -- verified here only as "the column allows
        completed -> pending," since the actual reset-on-rename logic lives in
        Unit 2, not this layer."""
        from transactagent_db.models import EmbeddingStatus

        payment = RecurringPayment(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=15,
            embedding_status=EmbeddingStatus.COMPLETED,
        )
        db_session.add(payment)
        db_session.flush()

        payment.name = "Gym Membership (Renamed)"
        payment.embedding_status = EmbeddingStatus.PENDING
        db_session.flush()
        db_session.refresh(payment)

        assert payment.embedding_status == EmbeddingStatus.PENDING


class TestRecurringPaymentMatch:
    """Epic 8. BR-21 (at most one live match per recurring_payment_id + cycle_period)
    is a raw-SQL partial unique index applied via Alembic (migrations/versions/
    0007_recurring_payments.py), not by anything Base.metadata.create_all() can
    create -- this file's fixtures build the schema via create_all() directly (see
    conftest.py), bypassing Alembic entirely. Same reasoning as BR-10/BR-14 having
    no unit test here either -- both verified at the Alembic-migration/integration
    level instead. Tests below cover what IS testable through the ORM at this layer.
    """

    def _make_payment(self, session, **overrides):
        defaults = dict(
            name="Gym Membership",
            expected_amount=Decimal("80.00"),
            frequency=RecurringPaymentFrequency.MONTHLY,
            due_day=15,
        )
        defaults.update(overrides)
        payment = RecurringPayment(**defaults)
        session.add(payment)
        session.flush()
        return payment

    def _make_transaction(self, session, description="GYM MEMBERSHIP FEE"):
        import uuid as uuid_module

        from transactagent_db.models import Transaction

        category = _make_category(session, name=f"Placeholder {uuid_module.uuid4().hex[:8]}")
        statement = _make_bank_statement(session, pdf_content_hash=uuid_module.uuid4().hex + uuid_module.uuid4().hex[:32])
        return Transaction(
            **_base_transaction_kwargs(
                session,
                description=description,
                category=category,
                bank_statement=statement,
                out_flow=Decimal("80.00"),
                in_flow=None,
            )
        )

    def test_pending_match_is_valid(self, db_session):
        payment = self._make_payment(db_session)
        txn = self._make_transaction(db_session)
        db_session.add(txn)
        db_session.flush()

        match = RecurringPaymentMatch(
            recurring_payment_id=payment.id,
            transaction_id=txn.id,
            cycle_period="2026-08",
            status=RecurringPaymentMatchStatus.PENDING,
            amount_at_match=Decimal("80.00"),
        )
        db_session.add(match)
        db_session.flush()
        db_session.refresh(payment)
        db_session.refresh(txn)

        assert match.resolved_at is None
        assert match in payment.matches
        assert match in txn.recurring_payment_matches

    def test_auto_applied_match_is_valid(self, db_session):
        """FR-7: a trusted payment's close-amount match is created directly as
        auto_applied, never passing through pending."""
        payment = self._make_payment(db_session, is_trusted=True)
        txn = self._make_transaction(db_session)
        db_session.add(txn)
        db_session.flush()

        match = RecurringPaymentMatch(
            recurring_payment_id=payment.id,
            transaction_id=txn.id,
            cycle_period="2026-08",
            status=RecurringPaymentMatchStatus.AUTO_APPLIED,
            amount_at_match=Decimal("80.00"),
        )
        db_session.add(match)
        db_session.flush()  # should not raise

    def test_duplicate_live_match_same_cycle_via_orm_shape_is_representable(self, db_session):
        """Not a BR-21 enforcement test (that's Alembic-only, see class docstring) --
        just confirms two matches for the same payment+cycle are representable
        objects at the ORM layer, so the real constraint has something to reject
        when tested at the migration level."""
        payment = self._make_payment(db_session)
        txn1 = self._make_transaction(db_session, description="GYM MEMBERSHIP FEE")
        txn2 = self._make_transaction(db_session, description="GYM MEMBERSHIP FEE ADJ")
        db_session.add_all([txn1, txn2])
        db_session.flush()

        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn1.id,
                cycle_period="2026-08",
                status=RecurringPaymentMatchStatus.PENDING,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.flush()
        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn2.id,
                cycle_period="2026-08",
                status=RecurringPaymentMatchStatus.PENDING,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.flush()  # no DB-level rejection here -- BR-21 lives in Alembic, not create_all()

    def test_different_cycle_periods_both_valid(self, db_session):
        payment = self._make_payment(db_session)
        txn1 = self._make_transaction(db_session, description="GYM MEMBERSHIP FEE JUL")
        txn2 = self._make_transaction(db_session, description="GYM MEMBERSHIP FEE AUG")
        db_session.add_all([txn1, txn2])
        db_session.flush()

        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn1.id,
                cycle_period="2026-07",
                status=RecurringPaymentMatchStatus.APPROVED,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.add(
            RecurringPaymentMatch(
                recurring_payment_id=payment.id,
                transaction_id=txn2.id,
                cycle_period="2026-08",
                status=RecurringPaymentMatchStatus.PENDING,
                amount_at_match=Decimal("80.00"),
            )
        )
        db_session.flush()  # should not raise


class TestDetectionSuggestion:
    """Epic 8. BR-22 (description_pattern uniqueness) is a standard unique
    constraint created by Base.metadata.create_all() directly, so fully testable
    at this layer, unlike BR-21."""

    def test_new_suggestion_is_valid(self, db_session):
        suggestion = DetectionSuggestion(
            description_pattern="STREAMING SERVICE",
            suggested_amount=Decimal("15.00"),
            occurrence_count=3,
            status=DetectionSuggestionStatus.NEW,
        )
        db_session.add(suggestion)
        db_session.flush()  # should not raise

        assert suggestion.resolved_at is None

    def test_duplicate_description_pattern_is_rejected(self, db_session):
        """BR-22 -- the mechanism behind FR-13's sticky dismissal."""
        db_session.add(
            DetectionSuggestion(
                description_pattern="STREAMING SERVICE",
                suggested_amount=Decimal("15.00"),
                occurrence_count=3,
                status=DetectionSuggestionStatus.DISMISSED,
            )
        )
        db_session.flush()

        duplicate = DetectionSuggestion(
            description_pattern="STREAMING SERVICE",
            suggested_amount=Decimal("15.00"),
            occurrence_count=4,
            status=DetectionSuggestionStatus.NEW,
        )
        db_session.add(duplicate)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_different_patterns_both_valid(self, db_session):
        db_session.add(
            DetectionSuggestion(
                description_pattern="STREAMING SERVICE",
                suggested_amount=Decimal("15.00"),
                occurrence_count=3,
            )
        )
        db_session.add(
            DetectionSuggestion(
                description_pattern="GYM MEMBERSHIP",
                suggested_amount=Decimal("80.00"),
                occurrence_count=2,
            )
        )
        db_session.flush()  # should not raise

    def test_optional_suggested_category(self, db_session):
        category = _make_category(db_session, name="Subscriptions")
        suggestion = DetectionSuggestion(
            description_pattern="STREAMING SERVICE",
            suggested_amount=Decimal("15.00"),
            occurrence_count=3,
            suggested_category_id=category.id,
        )
        db_session.add(suggestion)
        db_session.flush()
        db_session.refresh(category)

        assert suggestion in category.suggested_in_detection_suggestions


class TestDetectionScanRun:
    """Epic 8 -- added retroactively during Ingestion Worker Code Generation to
    back isDetectionScanDueNow()'s due-check. Trivial single-column table."""

    def test_scan_run_row_is_valid(self, db_session):
        run = DetectionScanRun()
        db_session.add(run)
        db_session.flush()  # should not raise

        assert run.ran_at is not None

    def test_multiple_scan_runs_are_all_valid(self, db_session):
        db_session.add(DetectionScanRun())
        db_session.add(DetectionScanRun())
        db_session.flush()  # should not raise -- no uniqueness constraint, every attempt is its own row


class TestTransactionEmbeddingStatus:
    """Epic 9 (Local Embedding-Based Semantic Similarity), BR-24: one-way,
    two-state column. server_default='pending' is what unifies forward processing
    and the one-time historical backfill (FR-11) into a single mechanism -- this is
    exercised here as a DB-level default, not an application-level one, so it also
    covers rows inserted without the ORM ever setting the field."""

    def test_new_transaction_defaults_to_pending(self, db_session):
        from transactagent_db.models import EmbeddingStatus, Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("25.50"), in_flow=None))
        db_session.add(txn)
        db_session.flush()
        db_session.refresh(txn)

        assert txn.embedding_status == EmbeddingStatus.PENDING

    def test_can_transition_to_completed(self, db_session):
        from transactagent_db.models import EmbeddingStatus, Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("25.50"), in_flow=None))
        db_session.add(txn)
        db_session.flush()

        txn.embedding_status = EmbeddingStatus.COMPLETED
        db_session.flush()
        db_session.refresh(txn)

        assert txn.embedding_status == EmbeddingStatus.COMPLETED


class TestTransactionLlmSuggestedCategory:
    """Matching Precision Refinement, BR-26: write-once, nullable -- null means the
    always-on LLM classification step abstained (UNSURE) or its endpoint was
    unreachable at ingestion time, never a sentinel row. Distinct from category_id
    (the transaction's actual, currently-assigned category)."""

    def test_defaults_to_null(self, db_session):
        from transactagent_db.models import Transaction

        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("12.00"), in_flow=None))
        db_session.add(txn)
        db_session.flush()
        db_session.refresh(txn)

        assert txn.llm_suggested_category_id is None
        assert txn.llm_suggested_category is None

    def test_can_be_set_independently_of_category_id(self, db_session):
        """The LLM's own classification (llm_suggested_category) and the transaction's
        actual assigned category (category) are two distinct FKs to Category -- they
        can legitimately point at different rows (that's precisely what a genuine
        disagreement, FR-MPR-6, means)."""
        from transactagent_db.models import Transaction

        assigned_category = _make_category(db_session, name="Groceries")
        llm_category = _make_category(db_session, name="Dining")

        txn = Transaction(
            **_base_transaction_kwargs(
                db_session, out_flow=Decimal("12.00"), in_flow=None, category=assigned_category
            )
        )
        db_session.add(txn)
        db_session.flush()

        txn.llm_suggested_category_id = llm_category.id
        db_session.flush()
        db_session.refresh(txn)
        db_session.refresh(assigned_category)
        db_session.refresh(llm_category)

        assert txn.category_id == assigned_category.id
        assert txn.llm_suggested_category_id == llm_category.id
        assert txn.llm_suggested_category_id != txn.category_id
        assert txn in assigned_category.transactions
        assert txn in llm_category.llm_suggested_in_transactions


class TestCategorizationDisagreement:
    """Matching Precision Refinement. Deliberately a standalone entity, not an
    extension of RecategorizationProposal -- see
    aidlc-docs/inception/plans/matching-precision-refinement-application-design-plan.md
    ("Key Design Resolution 1"). BR-27 (resolved_category_id must equal
    similarity_category_id or llm_category_id) is application-layer enforced (Unit 2),
    same precedent as BR-15/BR-16 on RecategorizationProposal -- not testable as a DB
    constraint here, same reasoning as TestRecategorizationProposal's docstring.
    """

    def _make_unrelated_transaction(self, session, description="AMAZON SG"):
        import uuid as uuid_module

        from transactagent_db.models import Transaction

        suffix = uuid_module.uuid4().hex
        category = _make_category(session, name=f"Placeholder {suffix[:8]}")
        statement = _make_bank_statement(session, pdf_content_hash=suffix.ljust(64, "0"))
        txn = Transaction(
            **_base_transaction_kwargs(
                session,
                description=description,
                out_flow=Decimal("18.00"),
                in_flow=None,
                category=category,
                bank_statement=statement,
            )
        )
        session.add(txn)
        session.flush()
        return txn

    def test_pending_disagreement_links_transaction_and_both_candidates(self, db_session):
        txn = self._make_unrelated_transaction(db_session)
        similarity_category = _make_category(db_session, name="Groceries")
        llm_category = _make_category(db_session, name="Dining")

        disagreement = CategorizationDisagreement(
            transaction_id=txn.id,
            similarity_category_id=similarity_category.id,
            llm_category_id=llm_category.id,
            similarity_score=Decimal("91.50"),
            status=CategorizationDisagreementStatus.PENDING,
        )
        db_session.add(disagreement)
        db_session.flush()
        db_session.refresh(txn)
        db_session.refresh(similarity_category)
        db_session.refresh(llm_category)

        assert disagreement.status == CategorizationDisagreementStatus.PENDING
        assert disagreement.resolved_category_id is None
        assert disagreement.resolved_at is None
        assert disagreement in txn.categorization_disagreements
        assert disagreement in similarity_category.similarity_in_categorization_disagreements
        assert disagreement in llm_category.llm_in_categorization_disagreements

    def test_resolved_disagreement_picks_one_of_the_two_candidates(self, db_session):
        """FR-MPR-10/11: resolving means picking one of the two offered candidates --
        here, the LLM's suggestion."""
        txn = self._make_unrelated_transaction(db_session)
        similarity_category = _make_category(db_session, name="Groceries")
        llm_category = _make_category(db_session, name="Dining")

        disagreement = CategorizationDisagreement(
            transaction_id=txn.id,
            similarity_category_id=similarity_category.id,
            llm_category_id=llm_category.id,
            similarity_score=Decimal("88.00"),
            status=CategorizationDisagreementStatus.RESOLVED,
            resolved_category_id=llm_category.id,
        )
        db_session.add(disagreement)
        db_session.flush()
        db_session.refresh(llm_category)

        assert disagreement.resolved_category_id == llm_category.id
        assert disagreement in llm_category.resolved_in_categorization_disagreements

    def test_rejected_disagreement_is_valid(self, db_session):
        """FR-RR-8-style no-memory policy: rejection leaves resolved_category_id null,
        no suppression record kept."""
        txn = self._make_unrelated_transaction(db_session)
        similarity_category = _make_category(db_session, name="Groceries")
        llm_category = _make_category(db_session, name="Dining")

        disagreement = CategorizationDisagreement(
            transaction_id=txn.id,
            similarity_category_id=similarity_category.id,
            llm_category_id=llm_category.id,
            similarity_score=Decimal("82.00"),
            status=CategorizationDisagreementStatus.REJECTED,
        )
        db_session.add(disagreement)
        db_session.flush()  # should not raise

        assert disagreement.resolved_category_id is None
