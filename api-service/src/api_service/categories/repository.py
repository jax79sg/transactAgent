"""Thin query wrappers for the Category entity (Repository Layer)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transactagent_db.models import Category, Transaction


def list_all(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.name)))


def list_all_with_usage_counts(db: Session) -> list[tuple[Category, int]]:
    """Alphabetical order preserved (unchanged existing contract for callers like the
    Settings page's category management list) -- the added count lets any consumer
    (e.g. the transaction-correction dropdown) re-sort by usage frequency itself
    without a second endpoint or query param."""
    stmt = (
        select(Category, func.count(Transaction.id).label("usage_count"))
        .outerjoin(Transaction, Transaction.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def find_by_id(db: Session, category_id: UUID) -> Category | None:
    return db.get(Category, category_id)


def find_by_name(db: Session, name: str) -> Category | None:
    return db.scalar(select(Category).where(Category.name == name))


def insert(db: Session, *, name: str, active: bool, is_reserved: bool) -> Category:
    category = Category(name=name, active=active, is_reserved=is_reserved)
    db.add(category)
    db.flush()
    return category


def rename(db: Session, category: Category, new_name: str) -> Category:
    category.name = new_name
    db.flush()
    return category


def deactivate(db: Session, category: Category) -> Category:
    category.active = False
    db.flush()
    return category


def count_transactions_using(db: Session, category_id: UUID) -> int:
    return db.scalar(select(func.count()).select_from(Transaction).where(Transaction.category_id == category_id)) or 0
