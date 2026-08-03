"""Aggregation queries for dashboards (Repository Layer)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from transactagent_db.models import Category, Transaction


def _month_expr():
    return func.to_char(Transaction.transaction_date, "YYYY-MM")


def _base_scope(db: Session, filters):
    conditions = [
        Transaction.transaction_date >= filters.date_from,
        Transaction.transaction_date <= filters.date_to,
        Transaction.conversion_unavailable.is_(False),
    ]
    if filters.currency is not None:
        conditions.append(Transaction.currency == filters.currency)
    return conditions


def category_trend_series(db: Session, filters) -> list[dict]:
    conditions = _base_scope(db, filters) + [Transaction.out_flow.is_not(None)]
    # month_expr is built once and reused for select/group_by/order_by: calling
    # _month_expr() separately for each clause creates distinct bound-parameter
    # expressions that Postgres does not recognize as equivalent for GROUP BY,
    # raising "column must appear in the GROUP BY clause" even though the SQL text
    # looks identical (caught by actually running this against Postgres).
    month_expr = _month_expr()
    stmt = (
        select(
            Category.name.label("category"),
            month_expr.label("month"),
            func.sum(Transaction.converted_amount_sgd).label("total_sgd"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(*conditions)
        .group_by(Category.name, month_expr)
        .order_by(month_expr)
    )
    return [{"category": r.category, "month": r.month, "total_sgd": r.total_sgd} for r in db.execute(stmt)]


def cash_flow_series(db: Session, filters) -> list[dict]:
    conditions = _base_scope(db, filters)
    month_expr = _month_expr()  # see category_trend_series for why this is built once
    # Two separate aggregates (income / expense) computed via conditional SUM for clarity
    stmt = (
        select(
            month_expr.label("month"),
            func.coalesce(
                func.sum(func.coalesce(Transaction.converted_amount_sgd, 0)).filter(Transaction.in_flow.is_not(None)),
                0,
            ).label("income_sgd"),
            func.coalesce(
                func.sum(func.coalesce(Transaction.converted_amount_sgd, 0)).filter(Transaction.out_flow.is_not(None)),
                0,
            ).label("expense_sgd"),
        )
        .select_from(Transaction)
        .where(*conditions)
        .group_by(month_expr)
        .order_by(month_expr)
    )
    return [
        {
            "month": r.month,
            "income_sgd": r.income_sgd,
            "expense_sgd": r.expense_sgd,
            "net_sgd": r.income_sgd - r.expense_sgd,
        }
        for r in db.execute(stmt)
    ]


def bank_breakdown_series(db: Session, filters) -> list[dict]:
    conditions = _base_scope(db, filters)
    month_expr = _month_expr()  # see category_trend_series for why this is built once
    stmt = (
        select(
            Transaction.bank_name.label("bank_name"),
            month_expr.label("month"),
            func.sum(func.coalesce(Transaction.converted_amount_sgd, 0)).label("total_sgd"),
        )
        .select_from(Transaction)
        .where(*conditions)
        .group_by(Transaction.bank_name, month_expr)
        .order_by(month_expr)
    )
    return [{"bank_name": r.bank_name, "month": r.month, "total_sgd": r.total_sgd} for r in db.execute(stmt)]


def conversion_disclosure(db: Session, filters) -> dict:
    scope = [
        Transaction.transaction_date >= filters.date_from,
        Transaction.transaction_date <= filters.date_to,
    ]
    if filters.currency is not None:
        scope.append(Transaction.currency == filters.currency)

    approximate_count = db.scalar(
        select(func.count()).select_from(Transaction).where(*scope, Transaction.conversion_is_approximate.is_(True))
    ) or 0
    excluded_ids = list(
        db.scalars(
            select(Transaction.id).where(*scope, Transaction.conversion_unavailable.is_(True))
        )
    )
    return {
        "approximate_count": approximate_count,
        "excluded_count": len(excluded_ids),
        "excluded_transaction_ids": excluded_ids,
    }
