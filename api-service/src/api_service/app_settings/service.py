"""Configuration Component addendum (Configurable Application Settings) --
list/get/update settings, restart guidance, and change history. Implements AR-28
through AR-33 (business-logic-model.md / business-rules.md).
"""

from dotenv import dotenv_values, set_key
from sqlalchemy.orm import Session

from api_service.app_settings import repository
from api_service.app_settings.catalog import SETTINGS_BY_NAME, SettingSpec
from api_service.app_settings.validation import check_cross_field, parse_and_validate
from api_service.config import SETTINGS_OVERRIDE_FILE
from api_service.errors import InvalidSettingValueError, UnknownSettingError
from transactagent_db.models import SettingOwningService

# AR-30: fixed strings, matching docker-compose.yml's container_name values. Never
# executed by this service -- no Docker-socket access exists (Resolved Decision 2).
_RESTART_COMMANDS: dict[SettingOwningService, str] = {
    SettingOwningService.INGESTION_WORKER: "docker restart transactagent-worker",
    SettingOwningService.API_SERVICE: "docker restart transactagent-api",
}

_ENV_KEY = lambda name: name.upper()  # noqa: E731 -- matches config.py's env var naming 1:1


def _override_values() -> dict[str, str | None]:
    return dict(dotenv_values(SETTINGS_OVERRIDE_FILE))


def _effective_value_str(spec: SettingSpec, overrides: dict[str, str | None]) -> tuple[str, bool]:
    """Returns (value_as_string, is_overridden)."""
    raw = overrides.get(_ENV_KEY(spec.name))
    if raw is not None:
        return raw, True
    return str(spec.default), False


def _to_dto_dict(spec: SettingSpec, overrides: dict[str, str | None]) -> dict:
    value, is_overridden = _effective_value_str(spec, overrides)
    return {
        "name": spec.name,
        "value": value,
        "is_overridden": is_overridden,
        "owning_services": [s.value for s in spec.owning_services],
        "classification": spec.classification,
        "type": spec.type,
        "min": spec.min,
        "max": spec.max,
        "allowed_values": list(spec.allowed_values) if spec.allowed_values else None,
    }


def list_settings() -> list[dict]:
    overrides = _override_values()
    return [_to_dto_dict(spec, overrides) for spec in SETTINGS_BY_NAME.values()]


def get_setting(name: str) -> dict:
    spec = SETTINGS_BY_NAME.get(name)
    if spec is None:
        raise UnknownSettingError(f"Unknown setting '{name}'")
    return _to_dto_dict(spec, _override_values())


def get_restart_guidance(db: Session, name: str) -> list[dict]:
    spec = SETTINGS_BY_NAME.get(name)
    if spec is None:
        raise UnknownSettingError(f"Unknown setting '{name}'")
    worker_busy = repository.is_ingestion_worker_busy(db) if SettingOwningService.INGESTION_WORKER in spec.owning_services else None
    targets = []
    for service in spec.owning_services:
        target = {"owning_service": service.value, "restart_command": _RESTART_COMMANDS[service]}
        if service == SettingOwningService.INGESTION_WORKER:
            target["worker_busy"] = worker_busy
        targets.append(target)
    return targets


def update_setting(db: Session, name: str, raw_value: str) -> dict:
    spec = SETTINGS_BY_NAME.get(name)
    if spec is None:
        raise UnknownSettingError(f"Unknown setting '{name}'")

    parsed, error = parse_and_validate(spec, raw_value)
    if error is not None:
        raise InvalidSettingValueError(f"Invalid value for '{name}': {error}")

    if spec.cross_field is not None:
        partner_spec = SETTINGS_BY_NAME[spec.cross_field_partner]
        overrides = _override_values()
        partner_value_str, _ = _effective_value_str(partner_spec, overrides)
        partner_parsed, partner_error = parse_and_validate(partner_spec, partner_value_str)
        if partner_error is not None:  # pragma: no cover -- partner's own stored value should already be valid
            raise InvalidSettingValueError(f"Cannot validate '{name}': sibling '{partner_spec.name}' is invalid")
        cross_error = check_cross_field(spec, parsed, partner_parsed)
        if cross_error is not None:
            raise InvalidSettingValueError(f"Invalid value for '{name}': {cross_error}")

    # AR-33: validate fully (above) before writing anything.
    previous_value, _ = _effective_value_str(spec, _override_values())
    set_key(SETTINGS_OVERRIDE_FILE, _ENV_KEY(name), str(parsed), quote_mode="never")

    for service in spec.owning_services:
        repository.insert_change(
            db,
            setting_name=name,
            owning_service=service,
            previous_value=previous_value,
            new_value=str(parsed),
        )

    return {
        "setting": get_setting(name),
        "restart_guidance": get_restart_guidance(db, name),
    }


def list_setting_history(db: Session) -> list:
    return repository.list_changes(db)
