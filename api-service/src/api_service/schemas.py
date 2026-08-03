"""Shared Pydantic base model: serializes/accepts camelCase JSON (matching the DTO
field names documented in functional-design/domain-entities.md) while keeping
snake_case Python field names internally.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
