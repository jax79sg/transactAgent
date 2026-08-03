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

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    proposed_in_recategorization_proposals: Mapped[list["RecategorizationProposal"]] = relationship(
        back_populates="proposed_category"
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

    bank_statement: Mapped["BankStatement"] = relationship(back_populates="transactions")
    category: Mapped["Category"] = relationship(back_populates="transactions")
    fx_rate_used: Mapped["FxRateCache | None"] = relationship(back_populates="transactions")
    recategorization_jobs: Mapped[list["RecategorizationJob"]] = relationship(back_populates="source_transaction")
    recategorization_proposals: Mapped[list["RecategorizationProposal"]] = relationship(
        back_populates="candidate_transaction"
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
