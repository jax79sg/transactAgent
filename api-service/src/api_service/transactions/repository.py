"""Query construction for transaction filtering, grouping, and pagination (Repository Layer).

The filter-building logic here is a pure function of (query) -> SQLAlchemy clauses,
making it the natural target for property-based testing once the PBT framework is
selected in Unit 3's NFR Requirements (Partial PBT mode, per requirements.md NFR-5.2).
"""

import enum
from datetime import date
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, joinedload

from transactagent_db.models import Category, RecategorizationJob, RecategorizationJobStatus, Transaction


def _stringify_group_key(value: object) -> str:
    """group_by=categorySource selects Transaction.category_source directly, which
    SQLAlchemy deserializes back into a CategorySource enum member (not the plain
    string) since the column's Enum type is preserved through the raw select(). A
    plain str() on a `class X(str, Enum)` member returns "CategorySource.MANUAL",
    not "manual" -- Enum.__str__ wins over str.__str__ in the MRO despite the str
    mixin, a easy-to-miss quirk. Caught by explicitly checking str(enum member)
    empirically rather than assuming, given this app was already bitten once this
    session by a related enum-serialization assumption (see aidlc-docs/audit.md,
    the SQLAlchemy Enum values_callable fix)."""
    return value.value if isinstance(value, enum.Enum) else str(value)


def _apply_filters(stmt: Select, query) -> Select:
    if query.date_from is not None:
        stmt = stmt.where(Transaction.transaction_date >= query.date_from)
    if query.date_to is not None:
        stmt = stmt.where(Transaction.transaction_date <= query.date_to)
    if query.bank is not None:
        stmt = stmt.where(Transaction.bank_name == query.bank)
    if query.category is not None:
        stmt = stmt.join(Category, Transaction.category_id == Category.id).where(Category.name == query.category)
    if query.flow_direction == "in":
        stmt = stmt.where(Transaction.in_flow.is_not(None))
    elif query.flow_direction == "out":
        stmt = stmt.where(Transaction.out_flow.is_not(None))
    if query.currency is not None:
        stmt = stmt.where(Transaction.currency == query.currency)
    if query.text_search is not None:
        stmt = stmt.where(Transaction.description.ilike(f"%{query.text_search}%"))
    if query.category_source is not None:
        stmt = stmt.where(Transaction.category_source == query.category_source)
    return stmt


_SORT_COLUMNS = {
    "date": Transaction.transaction_date,
    "amount": func.coalesce(Transaction.out_flow, Transaction.in_flow),
    "bank": Transaction.bank_name,
}


def _apply_sort(stmt: Select, query) -> Select:
    if query.sort_by == "category":
        column = Category.name
        stmt = stmt.join(Category, Transaction.category_id == Category.id, isouter=True) if query.category is None else stmt
    else:
        column = _SORT_COLUMNS[query.sort_by]
    return stmt.order_by(column.desc() if query.sort_dir == "desc" else column.asc())


def query_transactions(db: Session, query, page: int, page_size: int) -> tuple[list[Transaction], int]:
    base = select(Transaction).options(joinedload(Transaction.category))
    base = _apply_filters(base, query)

    total_count = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    stmt = _apply_sort(base, query)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = list(db.scalars(stmt).unique())
    return items, total_count


def query_for_ai_context(
    db: Session, date_from: date | None, date_to: date | None, limit: int
) -> tuple[list[Transaction], bool]:
    """Ground-truth data for Ask AI (US-6.1): transactions in the given date range
    (or all transactions if both bounds are None), most recent first. Returns
    (transactions, truncated) -- `truncated` is True if more rows matched than
    `limit`, so the caller can disclose that the AI's answer only saw a subset."""
    stmt = select(Transaction).options(joinedload(Transaction.category))
    if date_from is not None:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    stmt = stmt.order_by(Transaction.transaction_date.desc()).limit(limit + 1)

    rows = list(db.scalars(stmt).unique())
    truncated = len(rows) > limit
    return rows[:limit], truncated


def query_all_for_export(db: Session, filters, max_rows: int) -> list[Transaction]:
    stmt = select(Transaction).options(joinedload(Transaction.category))
    stmt = _apply_filters(stmt, filters)
    stmt = stmt.order_by(Transaction.transaction_date.desc()).limit(max_rows)
    return list(db.scalars(stmt).unique())


_GROUP_KEY_EXPRESSIONS = {
    "category": Category.name,
    "bank": Transaction.bank_name,
    "month": func.to_char(Transaction.transaction_date, "YYYY-MM"),
    "categorySource": Transaction.category_source,
}


def query_group_summaries(db: Session, query) -> list[dict]:
    group_expr = _GROUP_KEY_EXPRESSIONS[query.group_by]
    stmt = (
        select(
            group_expr.label("group_key"),
            func.coalesce(func.sum(Transaction.out_flow), 0).label("subtotal_out_flow"),
            func.coalesce(func.sum(Transaction.in_flow), 0).label("subtotal_in_flow"),
            func.count().label("transaction_count"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
    )
    stmt = _apply_filters(stmt, query)
    stmt = stmt.group_by(group_expr)

    return [
        {
            "group_key": _stringify_group_key(row.group_key),
            "group_label": _stringify_group_key(row.group_key),
            "subtotal_out_flow_sgd": row.subtotal_out_flow,
            "subtotal_in_flow_sgd": row.subtotal_in_flow,
            "transaction_count": row.transaction_count,
        }
        for row in db.execute(stmt)
    ]


def find_by_id(db: Session, transaction_id: UUID) -> Transaction | None:
    return db.get(Transaction, transaction_id, options=[joinedload(Transaction.category)])


def create_recategorization_job(db: Session, *, source_transaction_id: UUID) -> RecategorizationJob:
    job = RecategorizationJob(
        source_transaction_id=source_transaction_id,
        status=RecategorizationJobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    return job
