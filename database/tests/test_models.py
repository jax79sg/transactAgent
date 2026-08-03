"""Example-based tests verifying the schema enforces its documented business rules.

PBT is not applied to this unit (see database-code-generation-plan.md — no pure
transformation functions exist here; this unit is declarative schema/constraints only).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from transactagent_db.models import (
    BankStatement,
    Category,
    CategorySource,
    FxRateCache,
    IngestionRunFile,
    IngestionRunFileOutcome,
    RecategorizationJob,
    RecategorizationProposal,
    RecategorizationProposalSourceBucket,
    RecategorizationProposalStatus,
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
