"""Pure validation functions for a proposed setting value against its AR-28 spec
(type/range) and AR-29 (cross-field constraints). No I/O -- keeps this independently
testable from the override-file/DB side of service.py."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from api_service.app_settings.catalog import SettingSpec

_CURRENCY_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _is_well_formed_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_format(spec: SettingSpec, value: str) -> str | None:
    """Returns an error message, or None if the format-specific check passes.
    Type/range checks (numeric bounds, enum membership) are handled separately in
    parse_and_validate below -- this function only covers the string `format` tag."""
    if spec.format == "currency_code":
        if not _CURRENCY_CODE_RE.match(value):
            return f"'{value}' is not a 3-letter uppercase currency code"
    elif spec.format == "url":
        if not _is_well_formed_url(value):
            return f"'{value}' is not a well-formed http(s) URL"
    elif spec.format == "url_or_empty":
        if value != "" and not _is_well_formed_url(value):
            return f"'{value}' must be empty or a well-formed http(s) URL"
    elif spec.format == "url_list":
        origins = [o.strip() for o in value.split(",") if o.strip()]
        if not origins:
            return "must contain at least one origin"
        for origin in origins:
            if not _is_well_formed_url(origin):
                return f"'{origin}' is not a well-formed http(s) URL"
    elif spec.format == "ascending_number_list":
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            return "must contain at least one boundary"
        try:
            numbers = [float(p) for p in parts]
        except ValueError:
            return f"'{value}' contains a non-numeric boundary"
        if any(n <= 0 for n in numbers):
            return "every boundary must be positive"
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            return "boundaries must be strictly ascending"
    elif spec.format == "non_empty":
        if not value.strip():
            return "must not be empty"
    return None


def parse_and_validate(spec: SettingSpec, raw_value: str) -> tuple[object | None, str | None]:
    """Returns (parsed_value, error_message) -- exactly one is None. parsed_value's
    type matches spec.type (float/int/str)."""
    if spec.type == "float":
        try:
            parsed = float(raw_value)
        except ValueError:
            return None, f"'{raw_value}' is not a number"
        if spec.min is not None:
            if spec.min_exclusive and parsed <= spec.min:
                return None, f"must be greater than {spec.min}"
            if not spec.min_exclusive and parsed < spec.min:
                return None, f"must be at least {spec.min}"
        if spec.max is not None and parsed > spec.max:
            return None, f"must be at most {spec.max}"
        return parsed, None

    if spec.type == "int":
        try:
            parsed = int(raw_value)
        except ValueError:
            return None, f"'{raw_value}' is not an integer"
        if spec.min is not None:
            if spec.min_exclusive and parsed <= spec.min:
                return None, f"must be greater than {spec.min}"
            if not spec.min_exclusive and parsed < spec.min:
                return None, f"must be at least {spec.min}"
        if spec.max is not None and parsed > spec.max:
            return None, f"must be at most {spec.max}"
        return parsed, None

    if spec.type == "enum":
        if raw_value not in (spec.allowed_values or ()):
            allowed = ", ".join(spec.allowed_values or ())
            return None, f"'{raw_value}' must be one of: {allowed}"
        return raw_value, None

    # spec.type == "string"
    error = validate_format(spec, raw_value)
    if error is not None:
        return None, error
    return raw_value, None


def check_cross_field(spec: SettingSpec, new_parsed: object, partner_current_value: object) -> str | None:
    """AR-29. `partner_current_value` is the sibling's current effective value,
    already parsed to its own type by the caller. Returns an error message, or None."""
    if spec.cross_field is None:
        return None
    if spec.cross_field == "less_than" and not (new_parsed < partner_current_value):
        return f"must be less than {spec.cross_field_partner} (currently {partner_current_value})"
    if spec.cross_field == "greater_than" and not (new_parsed > partner_current_value):
        return f"must be greater than {spec.cross_field_partner} (currently {partner_current_value})"
    if spec.cross_field == "less_or_equal" and not (new_parsed <= partner_current_value):
        return f"must be less than or equal to {spec.cross_field_partner} (currently {partner_current_value})"
    if spec.cross_field == "greater_or_equal" and not (new_parsed >= partner_current_value):
        return f"must be greater than or equal to {spec.cross_field_partner} (currently {partner_current_value})"
    return None
