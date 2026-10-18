"""Read-only queries against the shared database (NFR-CFT-2). Every function here
is a SELECT -- no `.add()`/`.flush()`/`.commit()` anywhere in this module, by design
(NFR Design: "Read-Only Session Discipline"), verified by test_repository.py's own
dedicated assertion.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased
from transactagent_db.models import (
    Category,
    CategorySource,
    RecategorizationProposal,
    RecategorizationProposalStatus,
    Transaction,
)


@dataclass(frozen=True)
class EligibleTransaction:
    transaction_id: UUID
    description: str
    amount_sgd: Decimal | None
    category_name: str
    category_source: CategorySource


def find_eligible_transactions(db: Session) -> list[EligibleTransaction]:
    """MTR-1: category_source='manual' OR (category_source='similarity' AND the
    transaction is referenced by an approved recategorization_proposals row).
    'llm'-sourced and 'unsure' transactions are always excluded.

    Deliberately does NOT filter out NULL converted_amount_sgd here -- that
    exclusion (MTR-2) happens in curate.py, where it's counted separately for the
    curation summary, not silently dropped inside this query.
    """
    approved_candidate_ids = select(RecategorizationProposal.candidate_transaction_id).where(
        RecategorizationProposal.status == RecategorizationProposalStatus.APPROVED
    )

    stmt = (
        select(Transaction, Category.name)
        .join(Category, Transaction.category_id == Category.id)
        .where(
            (Transaction.category_source == CategorySource.MANUAL)
            | (
                (Transaction.category_source == CategorySource.SIMILARITY)
                & Transaction.id.in_(approved_candidate_ids)
            )
        )
        .order_by(Transaction.id)  # MTR-4: deterministic ordering for the split step
    )

    return [
        EligibleTransaction(
            transaction_id=txn.id,
            description=txn.description,
            amount_sgd=txn.converted_amount_sgd,
            category_name=category_name,
            category_source=txn.category_source,
        )
        for txn, category_name in db.execute(stmt).all()
    ]


def list_active_category_names(db: Session) -> list[str]:
    """Byte-identical query to ingestion_worker.categorization.repository's function
    of the same name (active categories; UNSURE is excluded by the caller, not
    here -- same split of responsibility as that module's own
    categorization/service.py callers) -- MTR-5's prompt template needs the
    identical whitelist the live prompt uses."""
    stmt = select(Category.name).where(Category.active.is_(True))
    return list(db.execute(stmt).scalars().all())


@dataclass(frozen=True)
class LabelledTransaction:
    """Every transaction column a classifier could use, with the label and where it came from. Unlike
    EligibleTransaction this is not filtered: which labels to trust is the dataset builder's report to make,
    not a silent decision inside a query."""

    transaction_id: UUID
    transaction_date: date
    description: str
    out_flow: Decimal | None
    in_flow: Decimal | None
    currency: str
    bank_name: str
    converted_amount_sgd: Decimal | None
    conversion_is_approximate: bool
    conversion_unavailable: bool
    bank_statement_id: UUID
    statement_account_id: UUID | None
    category_id: UUID
    category_name: str
    category_source: CategorySource
    llm_suggested_category_name: str | None


def list_labelled_transactions(db: Session) -> list[LabelledTransaction]:
    """Every transaction, with its category name, how that category was assigned, and the language model's own
    first-pass suggestion (write-once, so it survives later manual changes). Ordered by id so the same database
    state always yields the same list."""
    suggested = aliased(Category)
    stmt = (
        select(Transaction, Category.name, suggested.name)
        .join(Category, Transaction.category_id == Category.id)
        .outerjoin(suggested, Transaction.llm_suggested_category_id == suggested.id)
        .order_by(Transaction.id)
    )
    return [
        LabelledTransaction(
            transaction_id=txn.id,
            transaction_date=txn.transaction_date,
            description=txn.description,
            out_flow=txn.out_flow,
            in_flow=txn.in_flow,
            currency=txn.currency,
            bank_name=txn.bank_name,
            converted_amount_sgd=txn.converted_amount_sgd,
            conversion_is_approximate=txn.conversion_is_approximate,
            conversion_unavailable=txn.conversion_unavailable,
            bank_statement_id=txn.bank_statement_id,
            statement_account_id=txn.statement_account_id,
            category_id=txn.category_id,
            category_name=category_name,
            category_source=txn.category_source,
            llm_suggested_category_name=suggested_name,
        )
        for txn, category_name, suggested_name in db.execute(stmt).all()
    ]
