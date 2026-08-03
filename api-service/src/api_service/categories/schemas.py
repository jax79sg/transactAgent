from uuid import UUID

from pydantic import BaseModel, Field

from api_service.schemas import CamelModel


class CategoryDTO(CamelModel):
    id: UUID
    name: str
    active: bool
    is_reserved: bool
    transaction_count: int


class AddCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class RenameCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
