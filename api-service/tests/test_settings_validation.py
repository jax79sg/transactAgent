"""Pure unit tests for app_settings/validation.py (AR-28/AR-29) -- no DB, no file I/O."""

import pytest

from api_service.app_settings.catalog import SETTINGS_BY_NAME
from api_service.app_settings.validation import check_cross_field, parse_and_validate


class TestFloatValidation:
    def test_valid_value_in_range(self):
        spec = SETTINGS_BY_NAME["similarity_threshold"]
        parsed, error = parse_and_validate(spec, "90.0")
        assert parsed == 90.0
        assert error is None

    def test_below_min_is_rejected(self):
        spec = SETTINGS_BY_NAME["similarity_threshold"]
        parsed, error = parse_and_validate(spec, "-1.0")
        assert parsed is None
        assert "at least" in error

    def test_above_max_is_rejected(self):
        spec = SETTINGS_BY_NAME["embedding_similarity_threshold"]
        parsed, error = parse_and_validate(spec, "1.5")
        assert parsed is None
        assert "at most" in error

    def test_non_numeric_is_rejected(self):
        spec = SETTINGS_BY_NAME["similarity_threshold"]
        parsed, error = parse_and_validate(spec, "not-a-number")
        assert parsed is None
        assert "not a number" in error

    def test_exclusive_min_boundary_is_rejected(self):
        """poll_interval_seconds must be > 0.0, not >= 0.0."""
        spec = SETTINGS_BY_NAME["poll_interval_seconds"]
        parsed, error = parse_and_validate(spec, "0.0")
        assert parsed is None
        assert "greater than" in error


class TestIntValidation:
    def test_valid_int_in_range(self):
        spec = SETTINGS_BY_NAME["backup_schedule_hour"]
        parsed, error = parse_and_validate(spec, "14")
        assert parsed == 14
        assert error is None

    def test_out_of_range_hour_is_rejected(self):
        spec = SETTINGS_BY_NAME["backup_schedule_hour"]
        parsed, error = parse_and_validate(spec, "24")
        assert parsed is None
        assert "at most" in error

    def test_float_string_is_rejected_for_int_field(self):
        spec = SETTINGS_BY_NAME["retry_max_attempts"]
        parsed, error = parse_and_validate(spec, "3.5")
        assert parsed is None
        assert "not an integer" in error


class TestEnumValidation:
    def test_valid_enum_value(self):
        spec = SETTINGS_BY_NAME["extraction_confidence_threshold"]
        parsed, error = parse_and_validate(spec, "high")
        assert parsed == "high"
        assert error is None

    def test_invalid_enum_value_is_rejected(self):
        spec = SETTINGS_BY_NAME["extraction_confidence_threshold"]
        parsed, error = parse_and_validate(spec, "extreme")
        assert parsed is None
        assert "must be one of" in error


class TestStringFormatValidation:
    def test_valid_currency_code(self):
        spec = SETTINGS_BY_NAME["reporting_currency"]
        parsed, error = parse_and_validate(spec, "USD")
        assert parsed == "USD"
        assert error is None

    def test_lowercase_currency_code_is_rejected(self):
        spec = SETTINGS_BY_NAME["reporting_currency"]
        parsed, error = parse_and_validate(spec, "usd")
        assert parsed is None
        assert error is not None

    def test_valid_url(self):
        spec = SETTINGS_BY_NAME["openrouter_base_url"]
        parsed, error = parse_and_validate(spec, "https://openrouter.ai/api/v1")
        assert parsed == "https://openrouter.ai/api/v1"
        assert error is None

    def test_malformed_url_is_rejected(self):
        spec = SETTINGS_BY_NAME["openrouter_base_url"]
        parsed, error = parse_and_validate(spec, "not a url")
        assert parsed is None
        assert error is not None

    def test_empty_string_valid_for_url_or_empty(self):
        spec = SETTINGS_BY_NAME["embedding_base_url"]
        parsed, error = parse_and_validate(spec, "")
        assert parsed == ""
        assert error is None

    def test_url_list_all_valid(self):
        spec = SETTINGS_BY_NAME["frontend_origin"]
        parsed, error = parse_and_validate(spec, "http://localhost:8787,http://192.168.1.50:8787")
        assert error is None
        assert parsed == "http://localhost:8787,http://192.168.1.50:8787"

    def test_url_list_one_malformed_entry_rejects_whole_value(self):
        spec = SETTINGS_BY_NAME["frontend_origin"]
        parsed, error = parse_and_validate(spec, "http://localhost:8787,not-a-url")
        assert parsed is None
        assert error is not None

    def test_ascending_number_list_valid(self):
        spec = SETTINGS_BY_NAME["embedding_price_bucket_boundaries"]
        parsed, error = parse_and_validate(spec, "1,5,10,50")
        assert parsed == "1,5,10,50"
        assert error is None

    def test_ascending_number_list_not_ascending_is_rejected(self):
        spec = SETTINGS_BY_NAME["embedding_price_bucket_boundaries"]
        parsed, error = parse_and_validate(spec, "1,10,5,50")
        assert parsed is None
        assert "ascending" in error

    def test_ascending_number_list_negative_is_rejected(self):
        spec = SETTINGS_BY_NAME["embedding_price_bucket_boundaries"]
        parsed, error = parse_and_validate(spec, "1,-5,10")
        assert parsed is None
        assert "positive" in error

    def test_non_empty_rejects_blank(self):
        spec = SETTINGS_BY_NAME["embedding_model"]
        parsed, error = parse_and_validate(spec, "   ")
        assert parsed is None
        assert "empty" in error


class TestCrossFieldValidation:
    def test_cadence_min_less_than_max_passes(self):
        spec = SETTINGS_BY_NAME["recurring_payment_detection_cadence_min_days"]
        error = check_cross_field(spec, 25, 35)
        assert error is None

    def test_cadence_min_not_less_than_max_fails(self):
        spec = SETTINGS_BY_NAME["recurring_payment_detection_cadence_min_days"]
        error = check_cross_field(spec, 40, 35)
        assert error is not None
        assert "less than" in error

    def test_page_size_less_or_equal_passes(self):
        spec = SETTINGS_BY_NAME["default_page_size"]
        error = check_cross_field(spec, 50, 200)
        assert error is None

    def test_page_size_exceeding_max_fails(self):
        spec = SETTINGS_BY_NAME["default_page_size"]
        error = check_cross_field(spec, 250, 200)
        assert error is not None

    def test_no_cross_field_constraint_is_a_no_op(self):
        spec = SETTINGS_BY_NAME["similarity_threshold"]
        assert check_cross_field(spec, 90.0, None) is None


def test_catalog_has_exactly_41_settings():
    assert len(SETTINGS_BY_NAME) == 41


def test_every_setting_has_a_category_and_description():
    for spec in SETTINGS_BY_NAME.values():
        assert spec.category, spec.name
        assert spec.description, spec.name


def test_every_setting_has_a_parseable_default():
    """Sanity check: every spec's own documented default must pass its own
    validation -- catches a typo'd default before it ever reaches a real user."""
    for spec in SETTINGS_BY_NAME.values():
        parsed, error = parse_and_validate(spec, str(spec.default))
        assert error is None, f"{spec.name}'s default {spec.default!r} fails its own validation: {error}"
