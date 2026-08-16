"""SQLAlchemy domain models for the Bank Transaction Insights App.

Implements the entities in aidlc-docs/construction/database/functional-design/domain-entities.md
and the constraints in aidlc-docs/construction/database/functional-design/business-rules.md.
Business rules that cannot be expressed as a standing SQL constraint (BR-5 exactly-one-reserved-row,
BR-6 inactive-category-not-selectable, BR-8's cross-table date comparison, BR-11, BR-12) are
enforced at the application layer (Units 2/3) and noted inline below.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MONEY = Numeric(18, 2)  # BR-13: fixed-point decimal, 2 decimal places


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _enum_type(enum_cls: type[enum.Enum]) -> Enum:
    """SQLAlchemy's Enum type defaults to storing the Python member NAME (e.g. "FAILED"),
    not its .value ("failed"), even for str-mixin enums. Every raw-SQL CHECK constraint,
    service-layer comparison, and JSON API response in this codebase compares against
    lowercase .value strings, so values_callable is required to keep the stored DB
    representation consistent with everything else. Caught by actually running the test
    suite against Postgres (a raw-SQL CHECK constraint referencing 'failed' otherwise
    fails at CREATE TABLE time, since the default-derived enum only contains uppercase
    names).
    """
    return Enum(enum_cls, values_callable=lambda cls: [member.value for member in cls])


class CategorySource(str, enum.Enum):
    SIMILARITY = "similarity"
    LLM = "llm"
    MANUAL = "manual"
    UNSURE = "unsure"


class IngestionRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionRunFileOutcome(str, enum.Enum):
    PROCESSED = "processed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"


class RecategorizationJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RecategorizationProposalSourceBucket(str, enum.Enum):
    """Epic 6 (Recategorization Review Panel) — which search bucket (FR-RR-1) a
    RecategorizationProposal's candidate came from."""

    UNSURE = "unsure"
    CATEGORIZED = "categorized"


class RecategorizationProposalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


class BackupRunOutcome(str, enum.Enum):
    """Epic 7 (Nightly Transaction Backup)."""

    SUCCESS = "success"
    FAILED = "failed"


class BackupRunFailureCategory(str, enum.Enum):
    """Epic 7 — which message the Backup Status Component shows (FR-10/FR-11):
    a reconnect-Drive prompt for DRIVE_CONNECTIVITY, a generic indicator for OTHER."""

    DRIVE_CONNECTIVITY = "drive_connectivity"
    OTHER = "other"


class RecurringPaymentFrequency(str, enum.Enum):
    """Epic 8 (Recurring Payments)."""

    MONTHLY = "monthly"
    ANNUAL = "annual"


class RecurringPaymentMatchStatus(str, enum.Enum):
    """Epic 8 — structurally the same shape as RecategorizationProposalStatus."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


class DetectionSuggestionStatus(str, enum.Enum):
    """Epic 8 — status transitions on one persistent row per pattern (BR-22),
    rather than a new row per re-scan; this is what makes FR-13's dismissal sticky."""

    NEW = "new"
    DISMISSED = "dismissed"
    ADDED = "added"


class EmbeddingStatus(str, enum.Enum):
    """Epic 9 (Local Embedding-Based Semantic Similarity). One-way, two-state (BR-24)
    -- no FAILED value; a transient failure just leaves a row PENDING for the next
    poll cycle to retry (FR-10)."""

    PENDING = "pending"
    COMPLETED = "completed"


class CategorizationDisagreementStatus(str, enum.Enum):
    """Matching Precision Refinement. Unlike RecategorizationProposalStatus, there is no
    AUTO_APPLIED value -- a genuine disagreement (FR-MPR-6's third bullet) is by
    definition the case where the system deliberately does not pick a side."""

    PENDING = "pending"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class User(Base):
    """Single-user login credential (FR-9.1/9.2, US-5.1)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(back_populates="triggered_by")


class Category(Base):
    """The 46-entry whitelist (45 user categories + UNSURE). Requirements.md Section 5."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", name="uq_categories_name"),)  # BR-4

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)  # BR-6 (soft delete)
    is_reserved: Mapped[bool] = mapped_column(default=False, nullable=False)  # BR-5, true only for UNSURE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category", foreign_keys="Transaction.category_id"
    )
    proposed_in_recategorization_proposals: Mapped[list["RecategorizationProposal"]] = relationship(
        back_populates="proposed_category"
    )
    recurring_payments: Mapped[list["RecurringPayment"]] = relationship(back_populates="category")
    suggested_in_detection_suggestions: Mapped[list["DetectionSuggestion"]] = relationship(
        back_populates="suggested_category"
    )
    # Matching Precision Refinement: Transaction now carries a second FK to categories
    # (llm_suggested_category_id, BR-26), and CategorizationDisagreement carries three
    # (similarity/llm/resolved) -- each relationship below needs an explicit
    # foreign_keys to disambiguate which FK it corresponds to.
    llm_suggested_in_transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="llm_suggested_category", foreign_keys="Transaction.llm_suggested_category_id"
    )
    similarity_in_categorization_disagreements: Mapped[list["CategorizationDisagreement"]] = relationship(
        back_populates="similarity_category", foreign_keys="CategorizationDisagreement.similarity_category_id"
    )
    llm_in_categorization_disagreements: Mapped[list["CategorizationDisagreement"]] = relationship(
        back_populates="llm_category", foreign_keys="CategorizationDisagreement.llm_category_id"
    )
    resolved_in_categorization_disagreements: Mapped[list["CategorizationDisagreement"]] = relationship(
        back_populates="resolved_category", foreign_keys="CategorizationDisagreement.resolved_category_id"
    )


class BankStatement(Base):
    """One row per successfully-processed statement PDF (FR-3.1/3.2/3.3)."""

    __tablename__ = "bank_statements"
    __table_args__ = (UniqueConstraint("pdf_content_hash", name="uq_bank_statements_pdf_content_hash"),)  # BR-3

    id: Mapped[uuid.UUID] = _uuid_pk()
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex digest
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="bank_statement")


class Transaction(Base):
    """The core transaction record (FR-4.1). Original and converted amounts both retained (FR-10.2)."""

    __tablename__ = "transactions"
    __table_args__ = (
        # BR-2: exactly one of out_flow / in_flow is a positive, non-null value
        CheckConstraint(
            "(out_flow IS NOT NULL AND out_flow > 0 AND in_flow IS NULL) OR "
            "(in_flow IS NOT NULL AND in_flow > 0 AND out_flow IS NULL)",
            name="ck_transactions_exactly_one_flow_direction",
        ),
        # BR-8: conversion_unavailable implies no converted amount / rate reference
        CheckConstraint(
            "conversion_unavailable = false OR (converted_amount_sgd IS NULL AND fx_rate_used_id IS NULL)",
            name="ck_transactions_unavailable_implies_no_amount",
        ),
        # BR-8: cannot be both unavailable and approximate
        CheckConstraint(
            "NOT (conversion_unavailable AND conversion_is_approximate)",
            name="ck_transactions_not_unavailable_and_approximate",
        ),
        Index("ix_transactions_transaction_date", "transaction_date"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_bank_name", "bank_name"),
        Index("ix_transactions_bank_statement_id", "bank_statement_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    bank_statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_statements.id"), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    out_flow: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    in_flow: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)  # BR-1
    category_source: Mapped[CategorySource] = mapped_column(_enum_type(CategorySource), nullable=False)
    converted_amount_sgd: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    conversion_is_approximate: Mapped[bool] = mapped_column(default=False, nullable=False)
    conversion_unavailable: Mapped[bool] = mapped_column(default=False, nullable=False)
    fx_rate_used_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fx_rate_cache.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        _enum_type(EmbeddingStatus), nullable=False, server_default=EmbeddingStatus.PENDING.value
    )  # BR-24
    # Matching Precision Refinement: write-once (BR-26), never updated after the
    # transaction is first persisted -- a historical record of the always-on LLM
    # classification step (FR-MPR-1), read back by the retroactive re-scan's
    # score-boost logic (FR-MPR-7). Null means the LLM abstained (UNSURE) or its
    # endpoint was unreachable at ingestion time -- never a sentinel row.
    llm_suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )

    bank_statement: Mapped["BankStatement"] = relationship(back_populates="transactions")
    category: Mapped["Category"] = relationship(back_populates="transactions", foreign_keys=[category_id])
    llm_suggested_category: Mapped["Category | None"] = relationship(
        back_populates="llm_suggested_in_transactions", foreign_keys=[llm_suggested_category_id]
    )
    fx_rate_used: Mapped["FxRateCache | None"] = relationship(back_populates="transactions")
    recategorization_jobs: Mapped[list["RecategorizationJob"]] = relationship(back_populates="source_transaction")
    recategorization_proposals: Mapped[list["RecategorizationProposal"]] = relationship(
        back_populates="candidate_transaction"
    )
    recurring_payment_matches: Mapped[list["RecurringPaymentMatch"]] = relationship(back_populates="transaction")
    categorization_disagreements: Mapped[list["CategorizationDisagreement"]] = relationship(
        back_populates="transaction"
    )


class FxRateCache(Base):
    """Cached historical FX rates (FR-10.3/10.4), keyed by currency pair + date."""

    __tablename__ = "fx_rate_cache"
    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_rate_cache_pair_date"),  # BR-7
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SGD")
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="fx_rate_used")


class IngestionRun(Base):
    """One row per manually-triggered ingestion run (FR-1.4, US-1.2/1.5).

    BR-10 (at most one run may be `queued` or `running` at a time) is enforced by a
    Postgres partial unique index on a constant expression, created directly via raw SQL
    in migrations/versions/0001_initial_schema.py — this pattern isn't expressible through
    standard SQLAlchemy Table/Column metadata, so it's not declared here.
    """

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    status: Mapped[IngestionRunStatus] = mapped_column(
        _enum_type(IngestionRunStatus), nullable=False, default=IngestionRunStatus.QUEUED
    )
    triggered_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files_found_count: Mapped[int] = mapped_column(default=0, nullable=False)
    files_processed_count: Mapped[int] = mapped_column(default=0, nullable=False)
    files_skipped_count: Mapped[int] = mapped_column(default=0, nullable=False)
    files_failed_count: Mapped[int] = mapped_column(default=0, nullable=False)
    # Set only by the API (user clicked Cancel); read only by the worker, which is
    # the sole writer of `status` -- this split avoids a write race between the two
    # separate processes that both touch this row while a run is active. The worker
    # checks it between files (never mid-file) and transitions to CANCELLED itself.
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    triggered_by: Mapped["User"] = relationship(back_populates="ingestion_runs")
    files: Mapped[list["IngestionRunFile"]] = relationship(back_populates="ingestion_run")


class IngestionRunFile(Base):
    """Per-file outcome within a run (US-1.5 drill-down, OCR/parse failure debugging)."""

    __tablename__ = "ingestion_run_files"
    __table_args__ = (
        # BR-9: a failed file must have a failure reason
        CheckConstraint(
            "outcome != 'failed' OR failure_reason IS NOT NULL",
            name="ck_ingestion_run_files_failed_requires_reason",
        ),
        Index("ix_ingestion_run_files_ingestion_run_id", "ingestion_run_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    drive_file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    outcome: Mapped[IngestionRunFileOutcome] = mapped_column(_enum_type(IngestionRunFileOutcome), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_statement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bank_statements.id"), nullable=True)
    transactions_extracted_count: Mapped[int | None] = mapped_column(nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingestion_run: Mapped["IngestionRun"] = relationship(back_populates="files")


class IngestionRunLog(Base):
    """Raw worker log lines captured while a run is active, for the live log-tail view
    in the Ingestion page (added 2026-08-01 after a user found run progress hard to
    read without seeing what the worker was actually doing -- see aidlc-docs/audit.md).

    A plain autoincrementing integer PK (not UUID, unlike every other table here) is
    deliberate: the frontend polls "give me log lines after id N", and an
    auto-incrementing integer gives a cheap, reliably-monotonic cursor for that --
    timestamps alone could collide or not be strictly ordered under rapid successive
    inserts.
    """

    __tablename__ = "ingestion_run_logs"
    __table_args__ = (Index("ix_ingestion_run_logs_run_id_id", "ingestion_run_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    logger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    ingestion_run: Mapped["IngestionRun"] = relationship()


class RecategorizationJob(Base):
    """FR-5.4 retroactive-recategorization job queue record."""

    __tablename__ = "recategorization_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    status: Mapped[RecategorizationJobStatus] = mapped_column(
        _enum_type(RecategorizationJobStatus), nullable=False, default=RecategorizationJobStatus.QUEUED
    )
    source_transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_transaction_count: Mapped[int | None] = mapped_column(nullable=True)

    source_transaction: Mapped["Transaction"] = relationship(back_populates="recategorization_jobs")
    proposals: Mapped[list["RecategorizationProposal"]] = relationship(back_populates="recategorization_job")


class RecategorizationProposal(Base):
    """Epic 6 (Recategorization Review Panel, added 2026-08-02) — one row per candidate
    match found by the broadened FR-5.4 search (FR-RR-1/2). `status = 'auto_applied'`
    rows are a historical record only (the match was written directly to `transactions`
    at creation time, per FR-RR-3); the Recategorization Review Component's list/count
    queries (US-6.4/US-6.6) only ever read `status = 'pending'` rows. See
    aidlc-docs/construction/database/functional-design/ for full design history.

    BR-14 (at most one pending proposal per candidate+job pair) is enforced by a Postgres
    partial unique index, created via raw SQL in
    migrations/versions/0004_recategorization_proposals.py — the same pattern used for
    BR-10 on ingestion_runs — since it isn't expressible through standard SQLAlchemy
    Table/Column metadata. BR-15 (a proposal's candidate must differ from its job's
    source transaction) and BR-16 (a proposal resolves out of `pending` exactly once)
    are enforced at the application layer (Units 2/3), not as standing SQL constraints.
    """

    __tablename__ = "recategorization_proposals"
    __table_args__ = (
        Index("ix_recategorization_proposals_job_id", "recategorization_job_id"),
        Index("ix_recategorization_proposals_candidate_transaction_id", "candidate_transaction_id"),
        Index("ix_recategorization_proposals_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    recategorization_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recategorization_jobs.id"), nullable=False
    )
    candidate_transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    proposed_category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
    match_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    source_bucket: Mapped[RecategorizationProposalSourceBucket] = mapped_column(
        _enum_type(RecategorizationProposalSourceBucket), nullable=False
    )
    status: Mapped[RecategorizationProposalStatus] = mapped_column(
        _enum_type(RecategorizationProposalStatus), nullable=False, default=RecategorizationProposalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recategorization_job: Mapped["RecategorizationJob"] = relationship(back_populates="proposals")
    candidate_transaction: Mapped["Transaction"] = relationship(back_populates="recategorization_proposals")
    proposed_category: Mapped["Category"] = relationship(back_populates="proposed_in_recategorization_proposals")


class CategorizationDisagreement(Base):
    """Matching Precision Refinement (added 2026-08-16) -- one row per genuine
    categorization disagreement (FR-MPR-6's third bullet: similarity matching AND the
    always-on LLM both confident, and they differ, FR-MPR-9). Deliberately a standalone
    entity, not an extension of RecategorizationProposal -- that entity is tied to a
    RecategorizationJob (a manual-correction event) which doesn't exist here, and
    carries exactly one proposed category where this needs two. See
    aidlc-docs/inception/plans/matching-precision-refinement-application-design-plan.md
    ("Key Design Resolution 1") for the full reasoning.

    BR-27 (resolved_category_id must equal similarity_category_id or llm_category_id)
    is enforced at the application layer (Unit 2, Recategorization Review Component),
    not as a standing SQL constraint -- same precedent as BR-15/BR-16 on
    RecategorizationProposal.
    """

    __tablename__ = "categorization_disagreements"
    __table_args__ = (
        Index("ix_categorization_disagreements_transaction_id", "transaction_id"),
        Index("ix_categorization_disagreements_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    similarity_category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
    llm_category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
    similarity_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[CategorizationDisagreementStatus] = mapped_column(
        _enum_type(CategorizationDisagreementStatus),
        nullable=False,
        default=CategorizationDisagreementStatus.PENDING,
    )
    resolved_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="categorization_disagreements")
    similarity_category: Mapped["Category"] = relationship(
        back_populates="similarity_in_categorization_disagreements", foreign_keys=[similarity_category_id]
    )
    llm_category: Mapped["Category"] = relationship(
        back_populates="llm_in_categorization_disagreements", foreign_keys=[llm_category_id]
    )
    resolved_category: Mapped["Category | None"] = relationship(
        back_populates="resolved_in_categorization_disagreements", foreign_keys=[resolved_category_id]
    )


class BackupRun(Base):
    """Epic 7 (Nightly Transaction Backup, added 2026-08-08) — one row per nightly
    backup attempt, written once by the Ingestion Worker's Backup Manager at
    completion, already in its terminal state. Unlike `IngestionRun`/
    `RecategorizationJob`, there is no `queued`/`running` interim status: a backup
    attempt is entirely synchronous within a single Ingestion Worker poll cycle
    (Application Design `services.md` addendum), not a cross-service handoff. See
    aidlc-docs/construction/database/functional-design/ for full design history.

    BR-17 (one attempt per calendar day) is enforced by a standard unique constraint
    on `backup_date` — unlike BR-10/BR-14, this doesn't need a partial index since
    the rule applies unconditionally to every row, not just rows in a particular
    status.
    """

    __tablename__ = "backup_runs"
    __table_args__ = (
        UniqueConstraint("backup_date", name="uq_backup_runs_backup_date"),  # BR-17
        CheckConstraint(
            "(outcome = 'success' AND failure_category IS NULL) OR "
            "(outcome = 'failed' AND failure_category IS NOT NULL)",
            name="ck_backup_runs_failure_category_consistency",
        ),  # BR-18
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    backup_date: Mapped[date] = mapped_column(Date, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[BackupRunOutcome] = mapped_column(_enum_type(BackupRunOutcome), nullable=False)
    failure_category: Mapped[BackupRunFailureCategory | None] = mapped_column(
        _enum_type(BackupRunFailureCategory), nullable=True
    )
    transaction_count: Mapped[int | None] = mapped_column(nullable=True)
    backup_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RecurringPayment(Base):
    """Epic 8 (Recurring Payments, added 2026-08-08) — the user-maintained register
    of expected recurring payments (FR-1..3). `is_trusted` gates FR-7's tolerance-
    based auto-apply and only ever transitions false -> true (never reverts) — set
    when the first RecurringPaymentMatch for this payment is approved. See
    aidlc-docs/construction/database/functional-design/ for full design history.

    BR-19 (annual requires due_month, monthly must not have one) and BR-20 (due_day
    1-31) are both standing CHECK constraints.
    """

    __tablename__ = "recurring_payments"
    __table_args__ = (
        CheckConstraint(
            "(frequency = 'annual' AND due_month IS NOT NULL) OR "
            "(frequency = 'monthly' AND due_month IS NULL)",
            name="ck_recurring_payments_due_month_matches_frequency",
        ),  # BR-19
        CheckConstraint(
            "due_day >= 1 AND due_day <= 31",
            name="ck_recurring_payments_due_day_range",
        ),  # BR-20
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    frequency: Mapped[RecurringPaymentFrequency] = mapped_column(
        _enum_type(RecurringPaymentFrequency), nullable=False
    )
    due_month: Mapped[int | None] = mapped_column(nullable=True)
    due_day: Mapped[int] = mapped_column(nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    is_trusted: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Epic 9 (Local Embedding-Based Semantic Similarity), added 2026-08-13 retroactively
    # during Ingestion Worker Service Functional Design/Code Generation -- see BR-25.
    # Unlike Transaction.embedding_status (BR-24), this field has two write paths: the
    # API Service resets it to PENDING on create or on any name-changing update, since
    # the Ingestion Worker's Embedding Manager is the only component that ever computes
    # and stores embeddings (name change invalidates whatever's already stored).
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        _enum_type(EmbeddingStatus), nullable=False, default=EmbeddingStatus.PENDING,
        server_default=EmbeddingStatus.PENDING.value,
    )

    category: Mapped["Category | None"] = relationship(back_populates="recurring_payments")
    matches: Mapped[list["RecurringPaymentMatch"]] = relationship(back_populates="recurring_payment")


class RecurringPaymentMatch(Base):
    """Epic 8 (added 2026-08-08) — one row per candidate match found by the
    Ingestion Worker's Recurring Payment Manager (FR-5). Structurally the closest
    sibling to RecategorizationProposal in this schema: `pending` resolves to
    `approved`/`rejected` via user action, or is created directly as `auto_applied`
    for a trusted payment within tolerance (FR-7). `cycle_period` (e.g. "2026-08"
    for monthly, "2026" for annual) plays the role recategorization_job_id plays
    there -- the grouping key BR-21's uniqueness rule uses.

    BR-21 (at most one live match per recurring_payment_id + cycle_period) is
    enforced by a raw-SQL partial unique index, applied via Alembic (same pattern
    as BR-10/BR-14), not expressible through standard SQLAlchemy Table/Column
    metadata. BR-23 (a match resolves out of pending exactly once) is enforced at
    the application layer (Unit 2), matching BR-16's precedent.
    """

    __tablename__ = "recurring_payment_matches"
    __table_args__ = (
        Index("ix_recurring_payment_matches_recurring_payment_id", "recurring_payment_id"),
        Index("ix_recurring_payment_matches_transaction_id", "transaction_id"),
        Index("ix_recurring_payment_matches_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    recurring_payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recurring_payments.id"), nullable=False)
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    cycle_period: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[RecurringPaymentMatchStatus] = mapped_column(
        _enum_type(RecurringPaymentMatchStatus), nullable=False, default=RecurringPaymentMatchStatus.PENDING
    )
    amount_at_match: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    recurring_payment: Mapped["RecurringPayment"] = relationship(back_populates="matches")
    transaction: Mapped["Transaction"] = relationship(back_populates="recurring_payment_matches")


class DetectionSuggestion(Base):
    """Epic 8 (added 2026-08-08) — untracked recurring-charge suggestions from the
    Recurring Payment Manager's periodic detection scan (FR-12). BR-22's unique
    constraint on description_pattern is the entire mechanism behind FR-13's sticky
    dismissal: one row exists per pattern for the database's lifetime, and its
    status transitions rather than a new row being inserted on every re-scan.
    """

    __tablename__ = "detection_suggestions"
    __table_args__ = (
        UniqueConstraint("description_pattern", name="uq_detection_suggestions_description_pattern"),  # BR-22
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    description_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    suggested_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[DetectionSuggestionStatus] = mapped_column(
        _enum_type(DetectionSuggestionStatus), nullable=False, default=DetectionSuggestionStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    suggested_category: Mapped["Category | None"] = relationship(back_populates="suggested_in_detection_suggestions")


class DetectionScanRun(Base):
    """Epic 8 (added 2026-08-08, retroactively during Ingestion Worker Code
    Generation -- see aidlc-docs/audit.md) -- one row per completed detection scan
    attempt (WR-19), the entity backing `isDetectionScanDueNow()`'s due-check
    (`services.md`'s poll_once() addendum already assumed this shape existed;
    Application/Functional Design left the backing entity unspecified). Write-once,
    same reasoning as BackupRun: a scan is entirely synchronous within one poll
    cycle, not a cross-service handoff, and has no failure-classification needs a
    backup attempt has (FR-10/FR-11) -- if a scan errors, simply no row is written
    and it remains due on the next poll cycle, which is harmless since scans are
    read-only until they insert new DetectionSuggestion rows.
    """

    __tablename__ = "detection_scan_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthCredential(Base):
    """Stores the refresh token from the one-time interactive Google OAuth consent
    (US-1.1), obtained via Unit 2's /drive/connect + /drive/callback endpoints and
    consumed by Unit 3's Drive Connector. Added retroactively during Unit 3's NFR
    Requirements after Functional Design left the OAuth mechanism underspecified —
    see aidlc-docs/audit.md 2026-08-01 for the full history of this addition.
    """

    __tablename__ = "oauth_credentials"
    __table_args__ = (UniqueConstraint("provider", name="uq_oauth_credentials_provider"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "google_drive"
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
