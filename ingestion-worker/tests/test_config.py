"""WR-33 (Configurable Application Settings): the settings-override file must take
precedence over process environment variables, and a missing/malformed-for-this-
service override file must never crash startup."""

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
