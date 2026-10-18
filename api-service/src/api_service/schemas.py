"""Shared Pydantic base model: serializes/accepts camelCase JSON (matching the DTO
field names documented in functional-design/domain-entities.md) while keeping
snake_case Python field names internally.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel

# Epic 13 (NFR-AB-1): an exact amount, always written to JSON as a string with two decimal places ("100.00"), never as
# a float, so a figure the screen shows is the figure the arithmetic produced.
Money = Annotated[Decimal, PlainSerializer(lambda value: f"{value:.2f}", return_type=str, when_used="json")]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)
