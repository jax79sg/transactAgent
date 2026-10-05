"""WR-33 (Configurable Application Settings): the settings-override file must take
precedence over process environment variables, and a missing/malformed-for-this-
service override file must never crash startup."""

import pytest
from pydantic import ValidationError

import ingestion_worker.config as config_module
from ingestion_worker.config import Settings


class TestSettingsOverrideFile:
    def test_missing_override_file_falls_back_to_process_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "does-not-exist.env"))
        monkeypatch.setenv("SIMILARITY_THRESHOLD", "77.0")

        settings = Settings()

        assert settings.similarity_threshold == 77.0

    def test_override_file_value_wins_over_process_env(self, tmp_path, monkeypatch):
        """The core WR-33 guarantee: without settings_customise_sources(), pydantic-
        settings' default precedence would let the process env value silently win
        instead -- verified empirically during Functional Design before this was
        implemented."""
        override_file = tmp_path / "settings.env"
        override_file.write_text("SIMILARITY_THRESHOLD=91.5\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))
        monkeypatch.setenv("SIMILARITY_THRESHOLD", "77.0")

        settings = Settings()

        assert settings.similarity_threshold == 91.5

    def test_override_file_unset_setting_falls_back_to_process_env(self, tmp_path, monkeypatch):
        """Only the keys actually present in the override file are overridden --
        everything else still flows from process env exactly as before."""
        override_file = tmp_path / "settings.env"
        override_file.write_text("SIMILARITY_THRESHOLD=91.5\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))
        monkeypatch.setenv("SIMILARITY_THRESHOLD", "77.0")
        monkeypatch.setenv("POLL_INTERVAL_SECONDS", "12.0")

        settings = Settings()

        assert settings.similarity_threshold == 91.5
        assert settings.poll_interval_seconds == 12.0

    def test_override_file_with_api_service_only_key_does_not_crash(self, tmp_path, monkeypatch):
        """The shared override file (Application Design) can contain keys owned by
        api-service, which ingestion-worker's Settings doesn't define as a field --
        must be silently ignored (extra='ignore'), not raise extra_forbidden."""
        override_file = tmp_path / "settings.env"
        override_file.write_text("JWT_EXPIRY_MINUTES=720\nSIMILARITY_THRESHOLD=91.5\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))

        settings = Settings()  # should not raise

        assert settings.similarity_threshold == 91.5
        assert not hasattr(settings, "jwt_expiry_minutes")


class TestDuplicateDetectionSettings:
    """WR-57: three settings, validated at startup."""

    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        for name in ("DUPLICATE_DETECTION_ENABLED", "DUPLICATE_MATCH_RATIO", "DUPLICATE_MIN_TRANSACTIONS"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings()

        assert settings.duplicate_detection_enabled is False  # ships OFF
        assert settings.duplicate_match_ratio == 0.80
        assert settings.duplicate_min_transactions == 3

    def test_boolean_accepts_the_catalogs_lowercase_values(self, tmp_path, monkeypatch):
        """The API's catalog stores the switch as the text `false` / `true`."""
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("DUPLICATE_DETECTION_ENABLED", "true")
        assert Settings().duplicate_detection_enabled is True
        monkeypatch.setenv("DUPLICATE_DETECTION_ENABLED", "false")
        assert Settings().duplicate_detection_enabled is False

    @pytest.mark.parametrize("ratio", ["0.50", "0.8", "1.0"])
    def test_ratio_within_bounds_is_accepted(self, tmp_path, monkeypatch, ratio):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("DUPLICATE_MATCH_RATIO", ratio)

        assert Settings().duplicate_match_ratio == float(ratio)

    @pytest.mark.parametrize("ratio", ["0.49", "0", "1.01", "-1"])
    def test_ratio_outside_bounds_stops_startup(self, tmp_path, monkeypatch, ratio):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("DUPLICATE_MATCH_RATIO", ratio)

        with pytest.raises(ValidationError):
            Settings()

    @pytest.mark.parametrize("minimum", ["1", "3", "50"])
    def test_minimum_within_bounds_is_accepted(self, tmp_path, monkeypatch, minimum):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("DUPLICATE_MIN_TRANSACTIONS", minimum)

        assert Settings().duplicate_min_transactions == int(minimum)

    @pytest.mark.parametrize("minimum", ["0", "51", "-2"])
    def test_minimum_outside_bounds_stops_startup(self, tmp_path, monkeypatch, minimum):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("DUPLICATE_MIN_TRANSACTIONS", minimum)

        with pytest.raises(ValidationError):
            Settings()

    def test_override_file_wins_for_the_new_names(self, tmp_path, monkeypatch):
        override_file = tmp_path / "settings.env"
        override_file.write_text("DUPLICATE_DETECTION_ENABLED=true\nDUPLICATE_MATCH_RATIO=0.9\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))
        monkeypatch.setenv("DUPLICATE_DETECTION_ENABLED", "false")
        monkeypatch.setenv("DUPLICATE_MATCH_RATIO", "0.7")

        settings = Settings()

        assert settings.duplicate_detection_enabled is True
        assert settings.duplicate_match_ratio == 0.9


class TestCategorizationProviderSetting:
    def test_defaults_to_local(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.delenv("CATEGORIZATION_PROVIDER", raising=False)

        assert Settings().categorization_provider == "local"

    @pytest.mark.parametrize("value", ["local", "gemini"])
    def test_accepts_the_two_values(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("CATEGORIZATION_PROVIDER", value)

        assert Settings().categorization_provider == value

    @pytest.mark.parametrize("value", ["openai", "Gemini", "", "true"])
    def test_anything_else_stops_startup_rather_than_silently_using_the_wrong_provider(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("CATEGORIZATION_PROVIDER", value)

        with pytest.raises(ValidationError):
            Settings()

    def test_the_settings_page_override_wins_over_the_deployed_value(self, tmp_path, monkeypatch):
        override_file = tmp_path / "settings.env"
        override_file.write_text("CATEGORIZATION_PROVIDER=gemini\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))
        monkeypatch.setenv("CATEGORIZATION_PROVIDER", "local")

        assert Settings().categorization_provider == "gemini"


class TestEmbeddingProviderSettings:
    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        for name in ("EMBEDDING_PROVIDER", "GEMINI_EMBEDDING_MODEL"):
            monkeypatch.delenv(name, raising=False)

        settings = Settings()

        assert settings.embedding_provider == "local"
        assert settings.gemini_embedding_model == "gemini-embedding-2"

    @pytest.mark.parametrize("value", ["local", "gemini"])
    def test_accepts_the_two_values(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("EMBEDDING_PROVIDER", value)

        assert Settings().embedding_provider == value

    @pytest.mark.parametrize("value", ["openai", "Gemini", "", "true"])
    def test_anything_else_stops_startup(self, tmp_path, monkeypatch, value):
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(tmp_path / "none.env"))
        monkeypatch.setenv("EMBEDDING_PROVIDER", value)

        with pytest.raises(ValidationError):
            Settings()

    def test_the_settings_page_override_wins_over_the_deployed_value(self, tmp_path, monkeypatch):
        override_file = tmp_path / "settings.env"
        override_file.write_text("EMBEDDING_PROVIDER=gemini\nGEMINI_EMBEDDING_MODEL=gemini-embedding-3\n")
        monkeypatch.setattr(config_module, "SETTINGS_OVERRIDE_FILE", str(override_file))
        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")

        settings = Settings()

        assert (settings.embedding_provider, settings.gemini_embedding_model) == ("gemini", "gemini-embedding-3")
