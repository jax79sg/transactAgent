from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from api_service.auth.dependencies import get_current_user_id
from api_service.categories import repository, service
from api_service.categories.schemas import (
    AddCategoryRequest,
    CategoryDTO,
    RenameCategoryRequest,
)
from api_service.db import get_db

router = APIRouter(prefix="/categories", tags=["categories"], dependencies=[Depends(get_current_user_id)])


def _to_dto(category, transaction_count: int) -> CategoryDTO:
    return CategoryDTO(
        id=category.id,
        name=category.name,
        active=category.active,
        is_reserved=category.is_reserved,
        transaction_count=transaction_count,
    )


@router.get("", response_model=list[CategoryDTO])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryDTO]:
    return [_to_dto(category, count) for category, count in service.list_categories(db)]


@router.post("", response_model=CategoryDTO, status_code=status.HTTP_201_CREATED)
def add_category(payload: AddCategoryRequest, db: Session = Depends(get_db)) -> CategoryDTO:
    category = service.add_category(db, payload.name)
    return _to_dto(category, 0)  # brand new -- cannot have any transactions yet


@router.put("/{category_id}", response_model=CategoryDTO)
def rename_category(category_id: UUID, payload: RenameCategoryRequest, db: Session = Depends(get_db)) -> CategoryDTO:
    category = service.rename_category(db, category_id, payload.name)
    return _to_dto(category, repository.count_transactions_using(db, category.id))


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(category_id: UUID, db: Session = Depends(get_db)) -> None:
    service.remove_category(db, category_id)
