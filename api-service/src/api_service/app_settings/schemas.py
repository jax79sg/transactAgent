from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from api_service.schemas import CamelModel


class SettingDTO(CamelModel):
    name: str
    value: str
    is_overridden: bool
    owning_services: list[str]
    classification: str
    category: str
    description: str
    type: str
    min: float | None = None
    max: float | None = None
    allowed_values: list[str] | None = None


class UpdateSettingRequest(BaseModel):
    value: str = Field(min_length=1)


class RestartTargetDTO(CamelModel):
    owning_service: str
    restart_command: str
    worker_busy: bool | None = None


class SettingChangeResultDTO(CamelModel):
    setting: SettingDTO
    restart_guidance: list[RestartTargetDTO]


class SettingChangeDTO(CamelModel):
    id: UUID
    setting_name: str
    owning_service: str
    previous_value: str | None
    new_value: str
    changed_at: datetime
