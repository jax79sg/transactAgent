from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_service.app_settings import service
from api_service.app_settings.schemas import (
    RestartTargetDTO,
    SettingChangeDTO,
    SettingChangeResultDTO,
    SettingDTO,
    UpdateSettingRequest,
)
from api_service.auth.dependencies import get_current_user_id
from api_service.db import get_db

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(get_current_user_id)])


# Registered before /{name} -- otherwise "history" would be captured as a setting name.
@router.get("/history", response_model=list[SettingChangeDTO])
def list_setting_history(db: Session = Depends(get_db)) -> list[SettingChangeDTO]:
    return [SettingChangeDTO.model_validate(change) for change in service.list_setting_history(db)]


@router.get("", response_model=list[SettingDTO])
def list_settings() -> list[SettingDTO]:
    return [SettingDTO(**item) for item in service.list_settings()]


@router.get("/{name}", response_model=SettingDTO)
def get_setting(name: str) -> SettingDTO:
    return SettingDTO(**service.get_setting(name))


@router.get("/{name}/restart-guidance", response_model=list[RestartTargetDTO], response_model_exclude_none=True)
def get_restart_guidance(name: str, db: Session = Depends(get_db)) -> list[RestartTargetDTO]:
    return [RestartTargetDTO(**target) for target in service.get_restart_guidance(db, name)]


@router.put("/{name}", response_model=SettingChangeResultDTO, response_model_exclude_none=True)
def update_setting(name: str, payload: UpdateSettingRequest, db: Session = Depends(get_db)) -> SettingChangeResultDTO:
    result = service.update_setting(db, name, payload.value)
    return SettingChangeResultDTO(
        setting=SettingDTO(**result["setting"]),
        restart_guidance=[RestartTargetDTO(**target) for target in result["restart_guidance"]],
    )
