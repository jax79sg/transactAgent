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


def test_catalog_has_exactly_53_settings():
    assert len(SETTINGS_BY_NAME) == 53


def test_every_setting_has_a_category_and_description():
    for spec in SETTINGS_BY_NAME.values():
        assert spec.category, spec.name
        assert spec.description, spec.name


def test_every_setting_has_a_parseable_default():
    """Sanity check: every spec's own documented default must pass its own
    validation -- catches a typo'd default before it ever reaches a real user."""
    for spec in SETTINGS_BY_NAME.values():
        _parsed, error = parse_and_validate(spec, str(spec.default))
        assert error is None, f"{spec.name}'s default {spec.default!r} fails its own validation: {error}"


class TestCategorizationProviderEntry:
    def test_is_an_enumerated_standard_worker_setting_defaulting_to_local(self):
        spec = SETTINGS_BY_NAME["categorization_provider"]
        assert (spec.type, spec.default, spec.allowed_values, spec.classification) == ("enum", "local", ("local", "gemini"), "standard")
        assert [o.name if hasattr(o, "name") else o for o in spec.owning_services] == [o.name if hasattr(o, "name") else o for o in SETTINGS_BY_NAME["openrouter_model"].owning_services]

    def test_the_description_says_what_gemini_means_for_cost_and_privacy(self):
        text = SETTINGS_BY_NAME["categorization_provider"].description
        assert "gemini_model" in text and "Google" in text and "UNSURE" in text and "restart" in text

    def test_the_local_endpoint_settings_say_they_apply_only_to_local(self):
        for name in ("openrouter_base_url", "openrouter_model"):
            assert "categorization_provider" in SETTINGS_BY_NAME[name].description

    @pytest.mark.parametrize("value", ["local", "gemini"])
    def test_accepts_the_two_values(self, value):
        parsed, error = parse_and_validate(SETTINGS_BY_NAME["categorization_provider"], value)
        assert error is None and parsed == value

    @pytest.mark.parametrize("value", ["openai", "Gemini", "", "true"])
    def test_rejects_anything_else(self, value):
        _parsed, error = parse_and_validate(SETTINGS_BY_NAME["categorization_provider"], value)
        assert error is not None


class TestEmbeddingProviderEntries:
    def test_embedding_provider_is_an_enumerated_standard_worker_setting_defaulting_to_local(self):
        spec = SETTINGS_BY_NAME["embedding_provider"]
        assert (spec.type, spec.default, spec.allowed_values, spec.classification) == ("enum", "local", ("local", "gemini"), "standard")
        assert spec.category == SETTINGS_BY_NAME["embedding_base_url"].category

    def test_the_description_covers_privacy_re_embedding_and_the_calibrated_thresholds(self):
        text = SETTINGS_BY_NAME["embedding_provider"].description
        for needle in ("Google", "re-embedded", "embedding_similarity_threshold", "recategorization_auto_apply_threshold", "0.94", "99", "restarts"):
            assert needle in text, needle

    def test_the_model_setting_is_advanced_non_empty_and_defaults_to_gemini_embedding_2(self):
        spec = SETTINGS_BY_NAME["gemini_embedding_model"]
        assert (spec.default, spec.classification, spec.format) == ("gemini-embedding-2", "advanced", "non_empty")
        _parsed, error = parse_and_validate(spec, "")
        assert error is not None

    def test_the_local_endpoint_settings_say_they_apply_only_to_local(self):
        for name in ("embedding_base_url", "embedding_model"):
            assert "embedding_provider" in SETTINGS_BY_NAME[name].description

    @pytest.mark.parametrize("value", ["local", "gemini"])
    def test_provider_accepts_the_two_values(self, value):
        parsed, error = parse_and_validate(SETTINGS_BY_NAME["embedding_provider"], value)
        assert error is None and parsed == value

    @pytest.mark.parametrize("value", ["openai", "Gemini", "", "true"])
    def test_provider_rejects_anything_else(self, value):
        _parsed, error = parse_and_validate(SETTINGS_BY_NAME["embedding_provider"], value)
        assert error is not None


class TestModelCostSettings:
    """Issue #28 (Costs page): the three prices a Gemini call is priced with."""

    _PRICES = ("gemini_input_price_per_million_usd", "gemini_output_price_per_million_usd",
               "gemini_embedding_price_per_million_usd")

    def test_defaults_are_googles_published_prices(self):
        assert [SETTINGS_BY_NAME[n].default for n in self._PRICES] == [0.30, 2.50, 0.20]

    def test_all_three_are_advanced_floats_in_their_own_category(self):
        for name in self._PRICES:
            spec = SETTINGS_BY_NAME[name]
            assert (spec.type, spec.classification, spec.category, spec.min) == ("float", "advanced", "Model Costs", 0.0)

    def test_the_text_prices_are_read_by_both_services_and_the_embedding_price_only_by_the_worker(self):
        both = {s.name for s in SETTINGS_BY_NAME["gemini_model"].owning_services}
        assert {s.name for s in SETTINGS_BY_NAME[self._PRICES[0]].owning_services} == both
        assert {s.name for s in SETTINGS_BY_NAME[self._PRICES[1]].owning_services} == both
        assert {s.name for s in SETTINGS_BY_NAME[self._PRICES[2]].owning_services} == {
            s.name for s in SETTINGS_BY_NAME["gemini_embedding_model"].owning_services
        }

    def test_the_descriptions_name_the_model_setting_they_go_with_and_the_price_list(self):
        assert "gemini_model" in SETTINGS_BY_NAME[self._PRICES[0]].description
        assert "pricing" in SETTINGS_BY_NAME[self._PRICES[0]].description
        assert "gemini_embedding_model" in SETTINGS_BY_NAME[self._PRICES[2]].description
        assert "estimated" in SETTINGS_BY_NAME[self._PRICES[2]].description

    @pytest.mark.parametrize("name", _PRICES)
    def test_a_free_price_is_valid_a_negative_or_non_numeric_one_is_not(self, name):
        spec = SETTINGS_BY_NAME[name]
        assert parse_and_validate(spec, "0")[1] is None
        assert parse_and_validate(spec, "0.075")[0] == 0.075
        assert "at least" in parse_and_validate(spec, "-0.01")[1]
        assert "not a number" in parse_and_validate(spec, "free")[1]

    def test_the_apis_own_defaults_match_the_catalog(self):
        from api_service.config import Settings

        fields = Settings.model_fields
        for name in self._PRICES:
            assert fields[name].default == SETTINGS_BY_NAME[name].default
