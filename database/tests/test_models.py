"""Example-based tests verifying the schema enforces its documented business rules.

PBT is not applied to this unit (see database-code-generation-plan.md — no pure
transformation functions exist here; this unit is declarative schema/constraints only).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table, text
from sqlalchemy.exc import IntegrityError

from transactagent_db.models import (
    Account,
    AccountKey,
    AccountType,
    BackupRun,
    BackupRunFailureCategory,
    BackupRunOutcome,
    BalanceAnchor,
    BankStatement,
    Base,
    CategorizationDisagreement,
    CategorizationDisagreementStatus,
    Category,
    CategorySource,
    ComparisonRowMarker,
    ComparisonSide,
    DetectionScanRun,
    DetectionSuggestion,
    DetectionSuggestionStatus,
    DuplicateComparison,
    DuplicateComparisonRow,
    DuplicatePair,
    DuplicatePairStatus,
    DuplicateScanState,
    FxRateCache,
    IngestionRunFile,
    IngestionRunFileOutcome,
    KnownFile,
    KnownFileState,
    ModelUsage,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
    RecurringPayment,
    RecurringPaymentFrequency,
    RecurringPaymentMatch,
    RecurringPaymentMatchStatus,
    SettingChange,
    SettingOwningService,
    StatementAccount,
    StatementRemovalJob,
    StatementRemovalJobStatus,
    Transaction,
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
    kwargs = {
        "bank_statement_id": statement.id,
        "transaction_date": date(2026, 1, 15),
        "description": "NTUC FAIRPRICE",
        "currency": "SGD",
        "bank_name": "DBS",
        "category_id": category.id,
        "category_source": CategorySource.SIMILARITY,
    }
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
        from datetime import datetime

        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username="account_owner", password_hash="hashed")
        db_session.add(user)
        db_session.flush()
        requested_at = datetime.now(UTC)
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
        return datetime.now(UTC)

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
        defaults = {
            "name": "Gym Membership",
            "expected_amount": Decimal("80.00"),
            "frequency": RecurringPaymentFrequency.MONTHLY,
            "due_day": 15,
        }
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


class TestSettingChange:
    """Configurable Application Settings (added 2026-08-16), BR-28/BR-29:
    standalone, append-only audit log -- no FK to any other entity, no DB-level
    allow-list (owned by the application layer, Unit 2's Configuration Component)."""

    def test_first_ever_change_has_null_previous_value(self, db_session):
        """A setting's first-ever recorded change has no prior SettingChange row to
        read a previous_value from -- null is the correct representation, not an
        empty string or the built-in default re-serialized."""
        change = SettingChange(
            setting_name="similarity_threshold",
            owning_service=SettingOwningService.INGESTION_WORKER,
            previous_value=None,
            new_value="90.0",
        )
        db_session.add(change)
        db_session.flush()  # should not raise

        assert change.previous_value is None
        assert change.new_value == "90.0"
        assert change.changed_at is not None

    def test_subsequent_change_records_previous_value(self, db_session):
        change = SettingChange(
            setting_name="poll_interval_seconds",
            owning_service=SettingOwningService.INGESTION_WORKER,
            previous_value="5.0",
            new_value="10.0",
        )
        db_session.add(change)
        db_session.flush()  # should not raise

        assert change.previous_value == "5.0"
        assert change.new_value == "10.0"

    def test_api_service_owned_setting_is_valid(self, db_session):
        change = SettingChange(
            setting_name="jwt_expiry_minutes",
            owning_service=SettingOwningService.API_SERVICE,
            previous_value="1440",
            new_value="720",
        )
        db_session.add(change)
        db_session.flush()  # should not raise

        assert change.owning_service == SettingOwningService.API_SERVICE

    def test_missing_new_value_is_rejected(self, db_session):
        change = SettingChange(
            setting_name="similarity_threshold",
            owning_service=SettingOwningService.INGESTION_WORKER,
            previous_value="85.0",
            new_value=None,
        )
        db_session.add(change)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_repeated_changes_to_same_setting_all_coexist(self, db_session):
        """BR-28/BR-29: no DB-level uniqueness or allow-list constraint -- every
        change is its own row, and the same setting_name may appear any number of
        times (that's the entire point of an append-only history)."""
        db_session.add(
            SettingChange(
                setting_name="similarity_threshold",
                owning_service=SettingOwningService.INGESTION_WORKER,
                previous_value="85.0",
                new_value="90.0",
            )
        )
        db_session.add(
            SettingChange(
                setting_name="similarity_threshold",
                owning_service=SettingOwningService.INGESTION_WORKER,
                previous_value="90.0",
                new_value="88.0",
            )
        )
        db_session.flush()  # should not raise -- two rows, same setting_name, both valid


def _make_account(session, **overrides):
    kwargs = {"name": "OCBC 360", "bank_name": "OCBC", "currency": "SGD"}
    kwargs.update(overrides)
    account = Account(**kwargs)
    session.add(account)
    session.flush()
    return account


def _make_account_key(session, account, **overrides):
    kwargs = {"account_id": account.id, "bank_key": "ocbc", "account_identifier": "501-123456-001", "currency": "SGD"}
    kwargs.update(overrides)
    key = AccountKey(**kwargs)
    session.add(key)
    session.flush()
    return key


class TestAccount:
    """Account Balance at a Point in Time (Epic 13, added 2026-10-02): the Account entity."""

    def test_defaults(self, db_session):
        account = _make_account(db_session)

        assert account.account_type == AccountType.UNKNOWN
        assert account.type_user_set is False
        assert account.created_at is not None
        assert account.updated_at is not None

    @pytest.mark.parametrize("account_type", list(AccountType))
    def test_every_account_type_is_valid(self, db_session, account_type):
        account = _make_account(db_session, account_type=account_type)
        assert account.account_type == account_type

    def test_database_defaults_apply_to_a_row_inserted_without_the_orm(self, db_session):
        """Raw-SQL inserts (a data migration, a one-off script) must get the same defaults
        as ORM inserts -- unknown type, type not user-set."""
        db_session.execute(
            text("INSERT INTO accounts (id, name, bank_name, currency) VALUES (gen_random_uuid(), 'x', 'y', 'SGD')")
        )
        row = db_session.execute(text("SELECT account_type, type_user_set FROM accounts WHERE name = 'x'")).one()

        assert row.account_type == "unknown"
        assert row.type_user_set is False


class TestAccountKeyUniqueness:
    """BR-30: at most one key per (bank_key, account_identifier, currency), where a
    MISSING identifier counts as its own distinct value."""

    def test_duplicate_key_with_identifier_is_rejected(self, db_session):
        first = _make_account(db_session, name="A")
        second = _make_account(db_session, name="B")
        _make_account_key(db_session, first)

        with pytest.raises(IntegrityError):
            _make_account_key(db_session, second)

    def test_duplicate_key_with_no_identifier_is_rejected(self, db_session):
        """The case an ordinary unique constraint would let through, since NULL != NULL --
        two identifier-less keys for the same bank and currency would otherwise coexist."""
        first = _make_account(db_session, name="A")
        second = _make_account(db_session, name="B")
        _make_account_key(db_session, first, account_identifier=None)

        with pytest.raises(IntegrityError):
            _make_account_key(db_session, second, account_identifier=None)

    def test_key_with_identifier_and_key_without_coexist(self, db_session):
        account = _make_account(db_session)
        _make_account_key(db_session, account, account_identifier="501-123456-001")
        _make_account_key(db_session, account, account_identifier=None)  # should not raise

    def test_same_identifier_in_two_currencies_coexist(self, db_session):
        sgd = _make_account(db_session, name="SGD", currency="SGD")
        usd = _make_account(db_session, name="USD", currency="USD")
        _make_account_key(db_session, sgd, currency="SGD")
        _make_account_key(db_session, usd, currency="USD")  # should not raise

    def test_different_identifiers_at_the_same_bank_coexist(self, db_session):
        first = _make_account(db_session, name="A")
        second = _make_account(db_session, name="B")
        _make_account_key(db_session, first, account_identifier="501-123456-001")
        _make_account_key(db_session, second, account_identifier="501-987654-001")  # should not raise

    def test_one_account_may_hold_several_keys_after_a_merge(self, db_session):
        """BR-35: a merge re-points the absorbed account's keys to the survivor, so a single
        account ends up recognized by several different bank keys."""
        account = _make_account(db_session)
        _make_account_key(db_session, account, bank_key="ocbc")
        _make_account_key(db_session, account, bank_key="ocbc bank")  # should not raise

        db_session.refresh(account)
        assert len(account.keys) == 2

    def test_key_requires_an_account(self, db_session):
        key = AccountKey(account_id=None, bank_key="ocbc", account_identifier="1", currency="SGD")
        db_session.add(key)
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestBalanceAnchor:
    """BR-32: at most one anchor per account, replaced in place."""

    def test_anchor_is_valid(self, db_session):
        account = _make_account(db_session)
        anchor = BalanceAnchor(account_id=account.id, balance=Decimal("12345.67"), as_of_date=date(2026, 9, 30))
        db_session.add(anchor)
        db_session.flush()  # should not raise

        assert anchor.created_at is not None

    def test_second_anchor_for_the_same_account_is_rejected(self, db_session):
        account = _make_account(db_session)
        db_session.add(BalanceAnchor(account_id=account.id, balance=Decimal("100.00"), as_of_date=date(2026, 1, 1)))
        db_session.flush()

        db_session.add(BalanceAnchor(account_id=account.id, balance=Decimal("200.00"), as_of_date=date(2026, 2, 1)))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_anchors_for_different_accounts_coexist(self, db_session):
        first = _make_account(db_session, name="A")
        second = _make_account(db_session, name="B")
        db_session.add(BalanceAnchor(account_id=first.id, balance=Decimal("100.00"), as_of_date=date(2026, 1, 1)))
        db_session.add(BalanceAnchor(account_id=second.id, balance=Decimal("200.00"), as_of_date=date(2026, 1, 1)))
        db_session.flush()  # should not raise

    def test_negative_balance_is_valid(self, db_session):
        """An overdrawn account has a negative balance; nothing forbids it."""
        account = _make_account(db_session)
        anchor = BalanceAnchor(account_id=account.id, balance=Decimal("-250.00"), as_of_date=date(2026, 1, 1))
        db_session.add(anchor)
        db_session.flush()  # should not raise

        assert anchor.balance == Decimal("-250.00")

    def test_replacing_in_place_is_valid(self, db_session):
        account = _make_account(db_session)
        anchor = BalanceAnchor(account_id=account.id, balance=Decimal("100.00"), as_of_date=date(2026, 1, 1))
        db_session.add(anchor)
        db_session.flush()

        anchor.balance = Decimal("999.99")
        anchor.as_of_date = date(2026, 6, 30)
        db_session.flush()  # should not raise
        db_session.refresh(anchor)

        assert anchor.balance == Decimal("999.99")
        assert anchor.as_of_date == date(2026, 6, 30)

    def test_anchor_requires_balance_and_date(self, db_session):
        account = _make_account(db_session)
        db_session.add(BalanceAnchor(account_id=account.id, balance=None, as_of_date=date(2026, 1, 1)))
        with pytest.raises(IntegrityError):
            db_session.flush()


def _make_section(session, statement, account, **overrides):
    section = StatementAccount(bank_statement_id=statement.id, account_id=account.id, **overrides)
    session.add(section)
    session.flush()
    return section


class TestStatementAccount:
    """Epic 13 Scope Change (several accounts per PDF): one row per account a statement
    holds, carrying that account's closing balance. BR-33 (balance and date together) and
    BR-37 (an account appears at most once per statement)."""

    def test_statement_without_any_section_is_valid(self, db_session):
        """Every statement ingested before the backfill looks like this."""
        statement = _make_bank_statement(db_session)
        db_session.refresh(statement)

        assert statement.statement_accounts == []

    def test_section_without_closing_balance_is_valid(self, db_session):
        statement = _make_bank_statement(db_session)
        section = _make_section(db_session, statement, _make_account(db_session))

        assert section.closing_balance is None
        assert section.closing_balance_date is None
        assert section.created_at is not None

    def test_closing_balance_and_date_together_is_valid(self, db_session):
        statement = _make_bank_statement(db_session)
        section = _make_section(
            db_session,
            statement,
            _make_account(db_session),
            closing_balance=Decimal("4321.09"),
            closing_balance_date=date(2026, 8, 31),
        )

        assert section.closing_balance == Decimal("4321.09")

    def test_negative_closing_balance_is_valid(self, db_session):
        """An overdrawn account prints a negative balance."""
        statement = _make_bank_statement(db_session)
        section = _make_section(
            db_session,
            statement,
            _make_account(db_session),
            closing_balance=Decimal("-12.50"),
            closing_balance_date=date(2026, 8, 31),
        )

        assert section.closing_balance == Decimal("-12.50")

    def test_closing_balance_without_date_is_rejected(self, db_session):
        statement = _make_bank_statement(db_session)
        account = _make_account(db_session)

        with pytest.raises(IntegrityError):
            _make_section(db_session, statement, account, closing_balance=Decimal("1.00"), closing_balance_date=None)

    def test_closing_balance_date_without_balance_is_rejected(self, db_session):
        statement = _make_bank_statement(db_session)
        account = _make_account(db_session)

        with pytest.raises(IntegrityError):
            _make_section(db_session, statement, account, closing_balance=None, closing_balance_date=date(2026, 8, 31))

    def test_same_account_twice_in_one_statement_is_rejected(self, db_session):
        """BR-37: a statement holds several DIFFERENT accounts, never the same one twice."""
        statement = _make_bank_statement(db_session)
        account = _make_account(db_session)
        _make_section(db_session, statement, account)

        with pytest.raises(IntegrityError):
            _make_section(db_session, statement, account)

    def test_two_different_accounts_in_one_statement_are_valid(self, db_session):
        """The whole point of the Scope Change: one PDF, several accounts."""
        statement = _make_bank_statement(db_session)
        _make_section(db_session, statement, _make_account(db_session, name="Savings"))
        _make_section(db_session, statement, _make_account(db_session, name="Current"))  # should not raise

        db_session.refresh(statement)
        assert len(statement.statement_accounts) == 2

    def test_same_account_on_two_statements_is_valid(self, db_session):
        account = _make_account(db_session)
        _make_section(db_session, _make_bank_statement(db_session, pdf_content_hash="1" * 64), account)
        _make_section(db_session, _make_bank_statement(db_session, pdf_content_hash="2" * 64), account)  # should not raise

        db_session.refresh(account)
        assert len(account.statement_accounts) == 2

    def test_section_requires_a_statement_and_an_account(self, db_session):
        account = _make_account(db_session)
        db_session.add(StatementAccount(bank_statement_id=None, account_id=account.id))
        with pytest.raises(IntegrityError):
            db_session.flush()


class TestTransactionStatementAccount:
    """BR-38: when a transaction is linked to a statement section, that section must belong
    to the transaction's OWN statement, or it would be attributed to the wrong account."""

    def _statement_with_section(self, db_session, content_hash, account):
        statement = _make_bank_statement(db_session, pdf_content_hash=content_hash)
        return statement, _make_section(db_session, statement, account)

    def test_transaction_without_a_section_is_valid(self, db_session):
        """Every transaction ingested before the backfill looks like this."""
        txn = Transaction(**_base_transaction_kwargs(db_session, out_flow=Decimal("10.00")))
        db_session.add(txn)
        db_session.flush()  # should not raise

        assert txn.statement_account_id is None

    def test_transaction_linked_to_a_section_of_its_own_statement_is_valid(self, db_session):
        statement, section = self._statement_with_section(db_session, "3" * 64, _make_account(db_session))
        txn = Transaction(
            **_base_transaction_kwargs(
                db_session, bank_statement=statement, statement_account_id=section.id, out_flow=Decimal("10.00")
            )
        )
        db_session.add(txn)
        db_session.flush()  # should not raise

        assert txn.statement_account_id == section.id

    def test_transaction_linked_to_another_statements_section_is_rejected(self, db_session):
        first_statement, _ = self._statement_with_section(db_session, "4" * 64, _make_account(db_session, name="A"))
        _, other_section = self._statement_with_section(db_session, "5" * 64, _make_account(db_session, name="B"))

        txn = Transaction(
            **_base_transaction_kwargs(
                db_session,
                bank_statement=first_statement,
                statement_account_id=other_section.id,
                out_flow=Decimal("10.00"),
            )
        )
        db_session.add(txn)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_two_sections_of_one_statement_each_get_their_own_transactions(self, db_session):
        statement = _make_bank_statement(db_session, pdf_content_hash="6" * 64)
        savings = _make_section(db_session, statement, _make_account(db_session, name="Savings"))
        current = _make_section(db_session, statement, _make_account(db_session, name="Current"))
        category = _make_category(db_session)

        for section in (savings, current):
            db_session.add(
                Transaction(
                    **_base_transaction_kwargs(
                        db_session,
                        bank_statement=statement,
                        category=category,
                        statement_account_id=section.id,
                        out_flow=Decimal("5.00"),
                    )
                )
            )
        db_session.flush()  # should not raise

        counts = db_session.execute(
            text("SELECT statement_account_id, count(*) FROM transactions WHERE bank_statement_id = :s GROUP BY 1"),
            {"s": statement.id},
        ).all()
        assert sorted(c for _, c in counts) == [1, 1]


class TestAccountDeletionRestricted:
    """BR-35 and BR-36, schema half: an account that still has sections, keys, or an anchor
    cannot be deleted; a section that still has transactions cannot be deleted; a statement
    that still has sections cannot be deleted. A merge must re-point everything first and
    delete last; the backfill must wipe in foreign-key order."""

    def test_account_with_a_section_cannot_be_deleted(self, db_session):
        account = _make_account(db_session)
        _make_section(db_session, _make_bank_statement(db_session), account)

        db_session.delete(account)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_account_with_a_key_cannot_be_deleted(self, db_session):
        account = _make_account(db_session)
        _make_account_key(db_session, account)

        db_session.delete(account)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_account_with_an_anchor_cannot_be_deleted(self, db_session):
        account = _make_account(db_session)
        db_session.add(BalanceAnchor(account_id=account.id, balance=Decimal("1.00"), as_of_date=date(2026, 1, 1)))
        db_session.flush()

        db_session.delete(account)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_statement_with_a_section_cannot_be_deleted(self, db_session):
        statement = _make_bank_statement(db_session)
        _make_section(db_session, statement, _make_account(db_session))

        db_session.delete(statement)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_section_with_a_transaction_cannot_be_deleted(self, db_session):
        statement = _make_bank_statement(db_session)
        section = _make_section(db_session, statement, _make_account(db_session))
        db_session.add(
            Transaction(
                **_base_transaction_kwargs(
                    db_session, bank_statement=statement, statement_account_id=section.id, out_flow=Decimal("1.00")
                )
            )
        )
        db_session.flush()

        db_session.delete(section)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_account_can_be_deleted_once_everything_is_re_pointed_or_removed(self, db_session):
        """The merge ordering BR-35 describes: re-point the sections and keys to the survivor,
        remove the absorbed account's anchor, then delete the now-empty account."""
        absorbed = _make_account(db_session, name="absorbed")
        survivor = _make_account(db_session, name="survivor")
        statement = _make_bank_statement(db_session)
        section = _make_section(db_session, statement, absorbed)
        key = _make_account_key(db_session, absorbed)
        anchor = BalanceAnchor(account_id=absorbed.id, balance=Decimal("1.00"), as_of_date=date(2026, 1, 1))
        db_session.add(anchor)
        db_session.flush()

        section.account_id = survivor.id
        key.account_id = survivor.id
        db_session.delete(anchor)
        db_session.flush()
        absorbed_id = absorbed.id
        db_session.delete(absorbed)
        db_session.flush()  # should not raise

        db_session.expire_all()
        assert db_session.get(Account, absorbed_id) is None
        assert db_session.get(AccountKey, key.id).account_id == survivor.id
        assert db_session.get(StatementAccount, section.id).account_id == survivor.id

    def test_backfill_wipe_order_succeeds(self, db_session):
        """BR-36: transactions, then sections, then statements -- each deletable once the one
        before it is gone, and the accounts (never wiped) are untouched."""
        account = _make_account(db_session)
        statement = _make_bank_statement(db_session)
        section = _make_section(db_session, statement, account)
        db_session.add(
            Transaction(
                **_base_transaction_kwargs(
                    db_session, bank_statement=statement, statement_account_id=section.id, out_flow=Decimal("1.00")
                )
            )
        )
        db_session.flush()

        db_session.execute(text("DELETE FROM transactions WHERE bank_statement_id = :s"), {"s": statement.id})
        db_session.execute(text("DELETE FROM statement_accounts WHERE bank_statement_id = :s"), {"s": statement.id})
        db_session.execute(text("DELETE FROM bank_statements WHERE id = :s"), {"s": statement.id})  # should not raise

        assert db_session.execute(text("SELECT count(*) FROM accounts WHERE id = :a"), {"a": account.id}).scalar() == 1


# --------------------------------------------------------------------------------------------
# Epic 14 (Probable Duplicate Statement Detection): BR-39..BR-52
# --------------------------------------------------------------------------------------------

_ACTIVE_JOB_STATUSES = [
    StatementRemovalJobStatus.QUEUED,
    StatementRemovalJobStatus.RUNNING,
    StatementRemovalJobStatus.EMBEDDINGS_PENDING,
]


def _make_comparison(session, **overrides):
    kwargs = {
        "earlier_content_hash": "e" * 64,
        "earlier_file_name": "JUN 2026_20260728074739457.pdf",
        "earlier_bank_name": "UOB",
        "earlier_period_start": date(2026, 6, 2),
        "earlier_period_end": date(2026, 6, 30),
        "earlier_transaction_count": 5,
        "later_content_hash": "f" * 64,
        "later_file_name": "JUN 2026_20260828174121571.pdf",
        "later_bank_name": "UOB",
        "later_period_start": date(2026, 6, 2),
        "later_period_end": date(2026, 6, 30),
        "later_transaction_count": 5,
        "matched_count": 5,
        "match_ratio": Decimal("1.0000"),
        "reason": "5 of 5 transactions match",
    }
    kwargs.update(overrides)
    comparison = DuplicateComparison(**kwargs)
    session.add(comparison)
    session.flush()
    return comparison


def _make_comparison_row(session, comparison, **overrides):
    kwargs = {
        "comparison_id": comparison.id,
        "side": ComparisonSide.EARLIER,
        "rank": 1,
        "transaction_date": date(2026, 6, 5),
        "description": "NTUC FAIRPRICE",
        "out_flow": Decimal("42.10"),
        "in_flow": None,
        "currency": "SGD",
        "marker": ComparisonRowMarker.ALSO_ON_OTHER,
    }
    kwargs.update(overrides)
    row = DuplicateComparisonRow(**kwargs)
    session.add(row)
    session.flush()
    return row


def _make_known_file(session, comparison, **overrides):
    kwargs = {
        "pdf_content_hash": "f" * 64,
        "state": KnownFileState.PROBABLE_DUPLICATE,
        "matched_statement_hash": "e" * 64,
        "comparison_id": comparison.id,
    }
    kwargs.update(overrides)
    known_file = KnownFile(**kwargs)
    session.add(known_file)
    session.flush()
    return known_file


def _make_pair(session, comparison, **overrides):
    kwargs = {
        "hash_a": "1" * 64,
        "hash_b": "2" * 64,
        "comparison_id": comparison.id,
        "keep_hash": "1" * 64,
        "removal_allowed": True,
    }
    kwargs.update(overrides)
    pair = DuplicatePair(**kwargs)
    session.add(pair)
    session.flush()
    return pair


def _make_removal_job(session, pair, **overrides):
    kwargs = {"pair_id": pair.id, "remove_statement_hash": pair.hash_b}
    kwargs.update(overrides)
    job = StatementRemovalJob(**kwargs)
    session.add(job)
    session.flush()
    return job


def _job_in_status(session, pair, status):
    """A removal job in `status`, with whatever BR-46 requires for that status."""
    extra = {}
    if status in (StatementRemovalJobStatus.EMBEDDINGS_PENDING, StatementRemovalJobStatus.EMBEDDINGS_FAILED):
        extra["removed_transaction_ids"] = [uuid.uuid4()]
    if status in (StatementRemovalJobStatus.FAILED, StatementRemovalJobStatus.EMBEDDINGS_FAILED):
        extra["failure_reason"] = "boom"
    return _make_removal_job(session, pair, status=status, **extra)


class TestIngestionRunFileProbableDuplicate:
    """BR-49: a file skipped as a probable duplicate carries its comparison and no statement."""

    def _run_file(self, session, **overrides):
        from transactagent_db.models import IngestionRun, IngestionRunStatus, User

        user = User(username=f"u-{uuid.uuid4().hex[:8]}", password_hash="x")
        session.add(user)
        session.flush()
        run = IngestionRun(triggered_by_user_id=user.id, status=IngestionRunStatus.COMPLETED)
        session.add(run)
        session.flush()
        kwargs = {
            "ingestion_run_id": run.id,
            "drive_file_id": "drive-9",
            "drive_file_name": "JUN 2026_20260828174121571.pdf",
            "outcome": IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE,
        }
        kwargs.update(overrides)
        run_file = IngestionRunFile(**kwargs)
        session.add(run_file)
        session.flush()
        return run_file

    def test_probable_duplicate_with_comparison_and_no_statement_is_valid(self, db_session):
        comparison = _make_comparison(db_session)
        run_file = self._run_file(db_session, duplicate_comparison_id=comparison.id)

        assert run_file.outcome is IngestionRunFileOutcome.SKIPPED_PROBABLE_DUPLICATE
        assert run_file.bank_statement_id is None

    def test_probable_duplicate_without_comparison_is_rejected(self, db_session):
        with pytest.raises(IntegrityError):
            self._run_file(db_session, duplicate_comparison_id=None)

    def test_other_outcome_with_a_comparison_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            self._run_file(
                db_session, outcome=IngestionRunFileOutcome.PROCESSED, duplicate_comparison_id=comparison.id
            )

    def test_probable_duplicate_with_a_statement_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        statement = _make_bank_statement(db_session)
        with pytest.raises(IntegrityError):
            self._run_file(db_session, duplicate_comparison_id=comparison.id, bank_statement_id=statement.id)

    def test_existing_outcomes_are_unaffected(self, db_session):
        statement = _make_bank_statement(db_session)
        processed = self._run_file(
            db_session, outcome=IngestionRunFileOutcome.PROCESSED, bank_statement_id=statement.id
        )
        skipped = self._run_file(
            db_session, outcome=IngestionRunFileOutcome.SKIPPED_DUPLICATE, bank_statement_id=statement.id
        )
        failed = self._run_file(db_session, outcome=IngestionRunFileOutcome.FAILED, failure_reason="no text")

        assert [processed.duplicate_comparison_id, skipped.duplicate_comparison_id, failed.duplicate_comparison_id] == [
            None,
            None,
            None,
        ]

    def test_comparison_referenced_by_a_run_file_cannot_be_deleted(self, db_session):
        comparison = _make_comparison(db_session)
        self._run_file(db_session, duplicate_comparison_id=comparison.id)

        with pytest.raises(IntegrityError):
            db_session.execute(text("DELETE FROM duplicate_comparisons WHERE id = :i"), {"i": comparison.id})


class TestKnownFile:
    """BR-39 (one record per hash) and BR-40 (every record carries its evidence)."""

    @pytest.mark.parametrize("state", list(KnownFileState))
    def test_a_valid_row_for_each_state(self, db_session, state):
        comparison = _make_comparison(db_session)
        known_file = _make_known_file(db_session, comparison, state=state)

        assert known_file.state is state
        assert known_file.decided_at is None
        assert known_file.created_at is not None

    def test_two_records_for_one_hash_are_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        _make_known_file(db_session, comparison)

        with pytest.raises(IntegrityError):
            _make_known_file(db_session, comparison, state=KnownFileState.OVERRIDDEN)

    def test_matched_hash_equal_to_own_hash_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_known_file(db_session, comparison, matched_statement_hash="f" * 64)

    def test_missing_matched_hash_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_known_file(db_session, comparison, matched_statement_hash=None)

    def test_missing_comparison_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_known_file(db_session, comparison, comparison_id=None)

    def test_unknown_comparison_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_known_file(db_session, comparison, comparison_id=uuid.uuid4())

    def test_state_accepts_only_the_three_values(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(Exception):  # noqa: B017 - a DBAPI error for an invalid enum label
            db_session.execute(
                text(
                    "INSERT INTO known_files (id, pdf_content_hash, state, matched_statement_hash, comparison_id) "
                    "VALUES (:id, :h, 'maybe', :m, :c)"
                ),
                {"id": uuid.uuid4(), "h": "9" * 64, "m": "8" * 64, "c": comparison.id},
            )

    def test_override_is_an_in_place_update_that_stamps_decided_at(self, db_session):
        comparison = _make_comparison(db_session)
        known_file = _make_known_file(db_session, comparison)

        known_file.state = KnownFileState.OVERRIDDEN
        known_file.decided_at = datetime.now(UTC)
        db_session.flush()
        db_session.refresh(known_file)

        assert known_file.state is KnownFileState.OVERRIDDEN
        assert known_file.decided_at is not None

    def test_comparison_referenced_by_a_known_file_cannot_be_deleted(self, db_session):
        comparison = _make_comparison(db_session)
        _make_known_file(db_session, comparison)

        with pytest.raises(IntegrityError):
            db_session.execute(text("DELETE FROM duplicate_comparisons WHERE id = :i"), {"i": comparison.id})


class TestDuplicateComparison:
    """BR-42: a comparison's bounds are enforced by the database."""

    def test_a_valid_comparison(self, db_session):
        comparison = _make_comparison(db_session)

        assert comparison.created_at is not None
        assert comparison.match_ratio == Decimal("1.0000")

    def test_file_name_and_bank_name_may_be_absent(self, db_session):
        """bank_statements stores no file name, so the label may not be resolvable."""
        comparison = _make_comparison(
            db_session, earlier_file_name=None, earlier_bank_name=None, later_file_name=None, later_bank_name=None
        )

        assert comparison.earlier_file_name is None

    def test_negative_transaction_count_is_rejected(self, db_session):
        with pytest.raises(IntegrityError):
            _make_comparison(db_session, earlier_transaction_count=-1, matched_count=0)

    def test_matched_count_equal_to_the_smaller_side_is_valid(self, db_session):
        comparison = _make_comparison(
            db_session, earlier_transaction_count=8, later_transaction_count=5, matched_count=5
        )

        assert comparison.matched_count == 5

    def test_matched_count_above_the_smaller_side_is_rejected(self, db_session):
        with pytest.raises(IntegrityError):
            _make_comparison(db_session, earlier_transaction_count=8, later_transaction_count=5, matched_count=6)

    def test_negative_matched_count_is_rejected(self, db_session):
        with pytest.raises(IntegrityError):
            _make_comparison(db_session, matched_count=-1)

    @pytest.mark.parametrize("ratio", [Decimal(0), Decimal("0.8000"), Decimal(1)])
    def test_ratio_within_zero_to_one_is_valid(self, db_session, ratio):
        comparison = _make_comparison(db_session, match_ratio=ratio)

        assert comparison.match_ratio == ratio

    @pytest.mark.parametrize("ratio", [Decimal("-0.0001"), Decimal("1.0001")])
    def test_ratio_outside_zero_to_one_is_rejected(self, db_session, ratio):
        with pytest.raises(IntegrityError):
            _make_comparison(db_session, match_ratio=ratio)

    def test_period_and_reason_are_required(self, db_session):
        with pytest.raises(IntegrityError):
            _make_comparison(db_session, later_period_start=None)


class TestDuplicateComparisonRow:
    """BR-42: at most 10 rows per side, each with exactly one positive flow."""

    def test_an_out_flow_row_and_an_in_flow_row_are_valid(self, db_session):
        comparison = _make_comparison(db_session)
        _make_comparison_row(db_session, comparison, rank=1)
        _make_comparison_row(db_session, comparison, rank=2, out_flow=None, in_flow=Decimal("3100.00"))

        db_session.refresh(comparison)
        assert len(comparison.rows) == 2

    def test_both_flows_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, out_flow=Decimal("1.00"), in_flow=Decimal("1.00"))

    def test_neither_flow_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, out_flow=None, in_flow=None)

    @pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("-5.00")])
    def test_a_non_positive_flow_is_rejected(self, db_session, amount):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, out_flow=amount)

    @pytest.mark.parametrize("rank", [1, 10])
    def test_rank_one_and_ten_are_valid(self, db_session, rank):
        comparison = _make_comparison(db_session)
        row = _make_comparison_row(db_session, comparison, rank=rank)

        assert row.rank == rank

    @pytest.mark.parametrize("rank", [0, 11])
    def test_rank_outside_one_to_ten_is_rejected(self, db_session, rank):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, rank=rank)

    def test_a_full_side_of_ten_rows_is_valid(self, db_session):
        comparison = _make_comparison(db_session)
        for rank in range(1, 11):
            _make_comparison_row(db_session, comparison, rank=rank)

        db_session.refresh(comparison)
        assert len(comparison.rows) == 10

    def test_the_same_rank_twice_on_one_side_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        _make_comparison_row(db_session, comparison, rank=3)

        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, rank=3)

    def test_the_same_rank_on_the_other_side_is_valid(self, db_session):
        comparison = _make_comparison(db_session)
        _make_comparison_row(db_session, comparison, side=ComparisonSide.EARLIER, rank=3)
        _make_comparison_row(
            db_session, comparison, side=ComparisonSide.LATER, rank=3, marker=ComparisonRowMarker.ONLY_ON_THIS_ONE
        )  # should not raise

    def test_a_row_requires_a_comparison(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_comparison_row(db_session, comparison, comparison_id=None)

    def test_deleting_a_comparison_deletes_its_rows(self, db_session):
        comparison = _make_comparison(db_session)
        _make_comparison_row(db_session, comparison, rank=1)
        _make_comparison_row(db_session, comparison, rank=2)

        db_session.execute(text("DELETE FROM duplicate_comparisons WHERE id = :i"), {"i": comparison.id})

        remaining = db_session.execute(
            text("SELECT count(*) FROM duplicate_comparison_rows WHERE comparison_id = :i"), {"i": comparison.id}
        ).scalar()
        assert remaining == 0


class TestDuplicatePair:
    """BR-43: a pair is unordered and unique, and its keep_hash is one of its two hashes."""

    def test_a_valid_pair_defaults_to_pending(self, db_session):
        comparison = _make_comparison(db_session)
        pair = _make_pair(db_session, comparison)

        assert pair.status is DuplicatePairStatus.PENDING
        assert pair.found_at is not None
        assert pair.decided_at is None

    @pytest.mark.parametrize("allowed", [True, False])
    def test_removal_allowed_round_trips_either_value(self, db_session, allowed):
        """BR-53: the worker's decision whether the panel offers removal for this pair."""
        comparison = _make_comparison(db_session)
        pair = _make_pair(db_session, comparison, removal_allowed=allowed)

        db_session.expire(pair)
        db_session.refresh(pair)

        assert pair.removal_allowed is allowed

    def test_removal_allowed_is_required(self, db_session):
        """No default: the writer must decide it, so a pair can never be created that silently
        offers (or withholds) removal."""
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, removal_allowed=None)

    def test_keep_hash_may_be_either_member(self, db_session):
        comparison = _make_comparison(db_session)
        pair = _make_pair(db_session, comparison, keep_hash="2" * 64)

        assert pair.keep_hash == "2" * 64

    def test_hashes_in_the_wrong_order_are_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, hash_a="2" * 64, hash_b="1" * 64, keep_hash="1" * 64)

    def test_equal_hashes_are_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, hash_a="1" * 64, hash_b="1" * 64)

    def test_order_uses_byte_order_not_the_servers_locale(self, db_session):
        """COLLATE "C": 'B' (0x42) sorts before 'a' (0x61) by bytes, though many locales
        sort 'a' before 'B'. The application compares in Python (byte order too), so the
        database must agree whatever its locale."""
        comparison = _make_comparison(db_session)
        pair = _make_pair(db_session, comparison, hash_a="B" * 64, hash_b="a" * 64, keep_hash="B" * 64)

        assert pair.hash_a == "B" * 64

    def test_the_ordering_constraint_pins_byte_order_in_its_definition(self, db_session):
        """The behavioural test above cannot tell the difference on a server whose default
        collation already is byte order (as the test container's is), so also check the
        stored definition: it must name COLLATE "C" explicitly."""
        definition = db_session.execute(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_duplicate_pairs_hashes_ordered'")
        ).scalar()

        assert definition is not None
        assert definition.count('COLLATE "C"') == 2, definition

    def test_byte_order_is_enforced_the_other_way_round_too(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, hash_a="a" * 64, hash_b="B" * 64, keep_hash="a" * 64)

    def test_the_same_pair_twice_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        _make_pair(db_session, comparison)

        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison)

    def test_two_pairs_sharing_one_statement_are_valid(self, db_session):
        """Three copies of one statement make three pairs."""
        comparison = _make_comparison(db_session)
        _make_pair(db_session, comparison, hash_a="1" * 64, hash_b="2" * 64, keep_hash="1" * 64)
        _make_pair(db_session, comparison, hash_a="1" * 64, hash_b="3" * 64, keep_hash="1" * 64)  # should not raise

    def test_keep_hash_outside_the_pair_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, keep_hash="3" * 64)

    def test_missing_comparison_is_rejected(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(IntegrityError):
            _make_pair(db_session, comparison, comparison_id=None)

    @pytest.mark.parametrize("status", list(DuplicatePairStatus))
    def test_every_status_is_storable(self, db_session, status):
        comparison = _make_comparison(db_session)
        pair = _make_pair(db_session, comparison, status=status)

        assert pair.status is status

    def test_status_accepts_only_the_four_values(self, db_session):
        comparison = _make_comparison(db_session)
        with pytest.raises(Exception):  # noqa: B017 - a DBAPI error for an invalid enum label
            db_session.execute(
                text(
                    "INSERT INTO duplicate_pairs (id, hash_a, hash_b, comparison_id, keep_hash, status) "
                    "VALUES (:id, :a, :b, :c, :a, 'maybe')"
                ),
                {"id": uuid.uuid4(), "a": "1" * 64, "b": "2" * 64, "c": comparison.id},
            )


class TestStatementRemovalJob:
    """BR-45 (one active job per pair) and BR-46 (a removal records its transactions)."""

    def test_defaults(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        job = _make_removal_job(db_session, pair)

        assert job.status is StatementRemovalJobStatus.QUEUED
        assert job.corrections_acknowledged == 0
        assert job.embedding_attempts == 0
        assert job.removed_transaction_ids is None
        assert job.deleted_counts is None
        assert job.requested_at is not None

    @pytest.mark.parametrize("first", _ACTIVE_JOB_STATUSES)
    @pytest.mark.parametrize("second", _ACTIVE_JOB_STATUSES)
    def test_two_active_jobs_for_one_pair_are_rejected(self, db_session, first, second):
        pair = _make_pair(db_session, _make_comparison(db_session))
        _job_in_status(db_session, pair, first)

        with pytest.raises(IntegrityError):
            _job_in_status(db_session, pair, second)

    @pytest.mark.parametrize(
        "finished", [StatementRemovalJobStatus.FAILED, StatementRemovalJobStatus.EMBEDDINGS_FAILED]
    )
    def test_a_failed_job_does_not_block_a_retry(self, db_session, finished):
        pair = _make_pair(db_session, _make_comparison(db_session))
        _job_in_status(db_session, pair, finished)

        retry = _job_in_status(db_session, pair, StatementRemovalJobStatus.QUEUED)  # should not raise

        assert retry.status is StatementRemovalJobStatus.QUEUED

    def test_a_completed_job_does_not_block_another_for_the_same_pair(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        _job_in_status(db_session, pair, StatementRemovalJobStatus.COMPLETED)

        _job_in_status(db_session, pair, StatementRemovalJobStatus.QUEUED)  # should not raise

    def test_active_jobs_for_different_pairs_are_valid(self, db_session):
        comparison = _make_comparison(db_session)
        first = _make_pair(db_session, comparison)
        second = _make_pair(db_session, comparison, hash_a="1" * 64, hash_b="3" * 64)
        _job_in_status(db_session, first, StatementRemovalJobStatus.QUEUED)
        _job_in_status(db_session, second, StatementRemovalJobStatus.QUEUED)  # should not raise

    @pytest.mark.parametrize(
        "status", [StatementRemovalJobStatus.EMBEDDINGS_PENDING, StatementRemovalJobStatus.EMBEDDINGS_FAILED]
    )
    def test_embedding_states_without_transaction_ids_are_rejected(self, db_session, status):
        pair = _make_pair(db_session, _make_comparison(db_session))
        with pytest.raises(IntegrityError):
            _make_removal_job(db_session, pair, status=status, failure_reason="x", removed_transaction_ids=None)

    @pytest.mark.parametrize(
        "status", [StatementRemovalJobStatus.FAILED, StatementRemovalJobStatus.EMBEDDINGS_FAILED]
    )
    def test_failed_states_without_a_reason_are_rejected(self, db_session, status):
        pair = _make_pair(db_session, _make_comparison(db_session))
        with pytest.raises(IntegrityError):
            _make_removal_job(db_session, pair, status=status, removed_transaction_ids=[uuid.uuid4()])

    def test_negative_counts_are_rejected(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        with pytest.raises(IntegrityError):
            _make_removal_job(db_session, pair, corrections_acknowledged=-1)

    def test_transaction_ids_and_counts_round_trip(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        counts = {"transactions": 3, "statement_accounts": 1, "recategorization_proposals": 0}
        job = _make_removal_job(
            db_session,
            pair,
            status=StatementRemovalJobStatus.EMBEDDINGS_PENDING,
            removed_transaction_ids=ids,
            deleted_counts=counts,
        )

        db_session.expire(job)
        db_session.refresh(job)

        assert job.removed_transaction_ids == ids
        assert job.deleted_counts == counts

    def test_removed_transaction_ids_have_no_foreign_key(self, db_session):
        """The rows are gone by the time the ids are recorded (BR-46)."""
        pair = _make_pair(db_session, _make_comparison(db_session))
        job = _make_removal_job(
            db_session,
            pair,
            status=StatementRemovalJobStatus.EMBEDDINGS_PENDING,
            removed_transaction_ids=[uuid.uuid4()],  # no such transaction exists
        )

        assert job.status is StatementRemovalJobStatus.EMBEDDINGS_PENDING

    def test_a_job_requires_a_pair(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        with pytest.raises(IntegrityError):
            _make_removal_job(db_session, pair, pair_id=None)

    def test_a_pair_with_a_job_cannot_be_deleted(self, db_session):
        pair = _make_pair(db_session, _make_comparison(db_session))
        _make_removal_job(db_session, pair)

        with pytest.raises(IntegrityError):
            db_session.execute(text("DELETE FROM duplicate_pairs WHERE id = :i"), {"i": pair.id})


class TestDuplicateScanState:
    """BR-48: exactly one row, with id 1."""

    def test_the_single_row_with_everything_unset_is_valid(self, db_session):
        db_session.add(DuplicateScanState(id=1))
        db_session.flush()
        state = db_session.get(DuplicateScanState, 1)

        assert state.last_scan_started_at is None
        assert state.last_scan_completed_at is None
        assert state.last_scan_match_ratio is None
        assert state.last_scan_min_transactions is None
        assert state.last_scan_pairs_found is None
        assert state.recheck_requested_at is None

    def test_the_row_holds_the_settings_of_the_last_scan(self, db_session):
        now = datetime.now(UTC)
        db_session.add(
            DuplicateScanState(
                id=1,
                last_scan_started_at=now,
                last_scan_completed_at=now,
                last_scan_match_ratio=Decimal("0.8000"),
                last_scan_min_transactions=3,
                last_scan_pairs_found=2,
                recheck_requested_at=now,
            )
        )
        db_session.flush()
        state = db_session.get(DuplicateScanState, 1)

        assert state.last_scan_match_ratio == Decimal("0.8000")
        assert state.last_scan_min_transactions == 3
        assert state.last_scan_pairs_found == 2

    def test_a_second_row_is_rejected(self, db_session):
        db_session.add(DuplicateScanState(id=1))
        db_session.flush()

        db_session.add(DuplicateScanState(id=2))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_a_duplicate_of_row_one_is_rejected(self, db_session):
        db_session.execute(text("INSERT INTO duplicate_scan_state (id) VALUES (1)"))

        with pytest.raises(IntegrityError):
            db_session.execute(text("INSERT INTO duplicate_scan_state (id) VALUES (1)"))


_STATEMENT_TABLES = frozenset({"bank_statements", "statement_accounts", "transactions"})
_EPIC_14_TABLES = frozenset(
    {
        "known_files",
        "duplicate_comparisons",
        "duplicate_comparison_rows",
        "duplicate_pairs",
        "statement_removal_jobs",
        "duplicate_scan_state",
    }
)
# BR-51: the tables that depend on a statement or its transactions. The first four are
# deleted (in WIPE_ORDER's order) by the Backfill Tool's wipe and by the Statement Removal
# Handler, and counted by the API's removal preview; the last is detached (set to null).
_KNOWN_DEPENDENTS = frozenset(
    {
        "recurring_payment_matches",
        "categorization_disagreements",
        "recategorization_proposals",
        "recategorization_jobs",
        "ingestion_run_files",
    }
)


def _dependents_of(metadata, targets):
    """Every table with a foreign-key path (including a transitive one) to any of `targets`,
    not counting the targets themselves."""
    references = {
        table.name: {fk.column.table.name for fk in table.foreign_keys} for table in metadata.tables.values()
    }
    found: set[str] = set()
    frontier = set(targets)
    while frontier:
        step = {
            name
            for name, referenced in references.items()
            if referenced & frontier and name not in found and name not in targets
        }
        found |= step
        frontier = step
    return found


class TestEpic14ReferencesByHash:
    """BR-50 and BR-51. Metadata-only: no database is needed."""

    def test_no_epic_14_table_has_a_foreign_key_to_a_statement_table(self):
        offenders = {
            f"{table.name} -> {fk.column.table.name}"
            for name in _EPIC_14_TABLES
            for table in [Base.metadata.tables[name]]
            for fk in table.foreign_keys
            if fk.column.table.name in _STATEMENT_TABLES
        }

        assert offenders == set(), (
            "Epic 14 tables must refer to statements by content hash, never by row id (BR-50): " f"{sorted(offenders)}"
        )

    def test_the_dependents_of_statements_and_transactions_are_exactly_the_known_list(self):
        found = _dependents_of(Base.metadata, _STATEMENT_TABLES)

        assert found == _KNOWN_DEPENDENTS, (
            f"Tables that now depend on statements or transactions: new {sorted(found - _KNOWN_DEPENDENTS)}, "
            f"gone {sorted(_KNOWN_DEPENDENTS - found)}. BR-51: update the Statement Removal Handler's cascade, "
            "the Backfill Tool's WIPE_ORDER, and the API's removal preview, then this list."
        )

    def test_the_dependents_check_follows_transitive_paths(self):
        """A table that only references a dependent (not a statement table) still counts."""
        metadata = MetaData()
        Table("parent", metadata, Column("id", Integer, primary_key=True))
        Table("child", metadata, Column("id", Integer, primary_key=True), Column("p", ForeignKey("parent.id")))
        Table("grandchild", metadata, Column("id", Integer, primary_key=True), Column("c", ForeignKey("child.id")))
        Table("unrelated", metadata, Column("id", Integer, primary_key=True))

        assert _dependents_of(metadata, {"parent"}) == {"child", "grandchild"}


class TestModelUsage:
    """Issue #28 (Model Cost Page): the standalone spend ledger. No foreign key to anything -- a row records money
    already spent, whatever later happened to the work that spent it."""

    @staticmethod
    def _row(**overrides) -> ModelUsage:
        fields = {
            "purpose": "categorization", "provider": "gemini", "model": "gemini-3.5-flash-lite",
            "input_tokens": 1200, "output_tokens": 40, "cost_usd": Decimal("0.00046000"),
        }
        fields.update(overrides)
        return ModelUsage(**fields)

    def test_a_row_is_valid_and_defaults_its_time_and_estimate_flag(self, db_session):
        row = self._row()
        db_session.add(row)
        db_session.flush()

        assert row.occurred_at is not None
        assert row.tokens_estimated is False
        assert row.id is not None

    def test_the_flag_for_estimated_tokens_round_trips(self, db_session):
        row = self._row(purpose="embedding", tokens_estimated=True)
        db_session.add(row)
        db_session.flush()
        db_session.expire(row)

        assert row.tokens_estimated is True

    def test_a_cost_of_a_few_millionths_of_a_dollar_is_not_rounded_away(self, db_session):
        """One embedding call costs about this much; the column must keep it."""
        row = self._row(purpose="embedding", cost_usd=Decimal("0.00000400"))
        db_session.add(row)
        db_session.flush()
        db_session.expire(row)

        assert row.cost_usd == Decimal("0.00000400")

    def test_a_free_call_with_zero_cost_is_valid(self, db_session):
        db_session.add(self._row(input_tokens=0, output_tokens=0, cost_usd=Decimal(0)))
        db_session.flush()  # should not raise

    @pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
    def test_negative_token_counts_are_rejected(self, db_session, field):
        db_session.add(self._row(**{field: -1}))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_a_negative_cost_is_rejected(self, db_session):
        db_session.add(self._row(cost_usd=Decimal("-0.01")))
        with pytest.raises(IntegrityError):
            db_session.flush()

    @pytest.mark.parametrize("field", ["purpose", "provider", "model", "input_tokens", "output_tokens", "cost_usd"])
    def test_every_descriptive_field_is_required(self, db_session, field):
        db_session.add(self._row(**{field: None}))
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_a_token_count_beyond_32_bits_is_storable(self, db_session):
        """A long backfill sums to billions of tokens; the count column must not be a 32-bit integer."""
        row = self._row(input_tokens=5_000_000_000)
        db_session.add(row)
        db_session.flush()  # should not raise

    def test_the_table_has_no_foreign_keys(self):
        assert not ModelUsage.__table__.foreign_keys
