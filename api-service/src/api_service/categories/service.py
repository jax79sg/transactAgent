"""Category CRUD business logic (business-logic-model.md — Configuration Component).

Implements AR-3 (reserved immutable), AR-4 (name uniqueness pre-check), AR-5 (blocked
while in use), and BR-6 (soft delete) at the application layer.
"""

from uuid import UUID

from sqlalchemy.orm import Session
from transactagent_db.models import Category

from api_service.categories import repository
from api_service.errors import (
    CategoryInUseError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
    ReservedCategoryError,
)


def list_categories(db: Session) -> list[tuple[Category, int]]:
    return repository.list_all_with_usage_counts(db)


def add_category(db: Session, name: str) -> Category:
    if repository.find_by_name(db, name) is not None:
        raise DuplicateCategoryNameError(f"Category '{name}' already exists")
    return repository.insert(db, name=name, active=True, is_reserved=False)


def rename_category(db: Session, category_id: UUID, new_name: str) -> Category:
    category = repository.find_by_id(db, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    if category.is_reserved:
        raise ReservedCategoryError("The reserved UNSURE category cannot be renamed")
    existing = repository.find_by_name(db, new_name)
    if existing is not None and existing.id != category_id:
        raise DuplicateCategoryNameError(f"Category '{new_name}' already exists")
    return repository.rename(db, category, new_name)


def remove_category(db: Session, category_id: UUID) -> None:
    category = repository.find_by_id(db, category_id)
    if category is None:
        raise CategoryNotFoundError(f"Category {category_id} not found")
    if category.is_reserved:
        raise ReservedCategoryError("The reserved UNSURE category cannot be removed")
    in_use_count = repository.count_transactions_using(db, category_id)
    if in_use_count > 0:
        raise CategoryInUseError(
            f"Cannot remove: {in_use_count} transactions still use this category",
            details={"blockedByTransactionCount": in_use_count},
        )
    repository.deactivate(db, category)
