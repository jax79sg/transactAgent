from datetime import UTC


class TestListSettingsApi:
    def test_requires_auth(self, client, settings_override_path):
        response = client.get("/settings")
        assert response.status_code == 401

    def test_returns_all_44_settings(self, client, auth_headers, settings_override_path):
        response = client.get("/settings", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 44
        names = {s["name"] for s in body}
        assert "similarity_threshold" in names
        assert "embedding_similarity_threshold" in names
        assert "ai_assistant_max_transactions" in names
        # Never reachable, under any name -- NFR-CAS-2.
        assert "db_password" not in names
        assert "jwt_secret" not in names
        assert "gemini_api_key" not in names

    def test_every_row_has_a_category_and_description(self, client, auth_headers, settings_override_path):
        response = client.get("/settings", headers=auth_headers)
        for row in response.json():
            assert row["category"], row["name"]
            assert row["description"], row["name"]

    def test_never_overridden_setting_reports_default_value(self, client, auth_headers, settings_override_path):
        response = client.get("/settings", headers=auth_headers)
        row = next(s for s in response.json() if s["name"] == "similarity_threshold")
        assert row["value"] == "85.0"
        assert row["isOverridden"] is False

    def test_never_overridden_worker_owned_setting_reflects_real_deployed_env_not_hardcoded_default(
        self, client, auth_headers, settings_override_path, monkeypatch
    ):
        """Regression coverage for the real bug found in live Build and Test: a
        deployment's real .env-configured value (e.g. OPENROUTER_MODEL set to a
        specific local model) was reported as the catalog's hardcoded default
        instead. `config.settings` -- fed the identical docker-compose env var as
        Ingestion Worker itself -- must be what's actually read."""
        import api_service.config as config_module

        monkeypatch.setattr(config_module.settings, "openrouter_model", "gemma-4-26b-a4b-it-4bit")

        response = client.get("/settings/openrouter_model", headers=auth_headers)
        assert response.json()["value"] == "gemma-4-26b-a4b-it-4bit"
        assert response.json()["isOverridden"] is False


class TestGetSettingApi:
    def test_unknown_setting_returns_404(self, client, auth_headers, settings_override_path):
        response = client.get("/settings/db_password", headers=auth_headers)
        assert response.status_code == 404

    def test_known_setting_returns_metadata(self, client, auth_headers, settings_override_path):
        response = client.get("/settings/embedding_similarity_threshold", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["classification"] == "advanced" or body["classification"] == "standard"
        assert body["type"] == "float"
        assert body["min"] == 0.0
        assert body["max"] == 1.0


class TestUpdateSettingApi:
    def test_valid_update_writes_override_and_returns_restart_guidance(
        self, client, auth_headers, settings_override_path
    ):
        response = client.put(
            "/settings/similarity_threshold", json={"value": "91.5"}, headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert body["setting"]["value"] == "91.5"
        assert body["setting"]["isOverridden"] is True
        assert body["restartGuidance"] == [
            {
                "owningService": "ingestion-worker",
                "restartCommand": "docker restart transactagent-worker",
                "workerBusy": False,
            }
        ]

        # Reflected on a subsequent read.
        get_response = client.get("/settings/similarity_threshold", headers=auth_headers)
        assert get_response.json()["value"] == "91.5"

    def test_invalid_value_is_rejected_and_not_written(self, client, auth_headers, settings_override_path):
        response = client.put(
            "/settings/similarity_threshold", json={"value": "not-a-number"}, headers=auth_headers
        )
        assert response.status_code == 400

        get_response = client.get("/settings/similarity_threshold", headers=auth_headers)
        assert get_response.json()["isOverridden"] is False  # untouched

    def test_unknown_setting_returns_404(self, client, auth_headers, settings_override_path):
        response = client.put("/settings/jwt_secret", json={"value": "hacked"}, headers=auth_headers)
        assert response.status_code == 404

    def test_cross_field_violation_is_rejected(self, client, auth_headers, settings_override_path):
        # default_page_size (50) must stay <= max_page_size (200, still default).
        response = client.put("/settings/default_page_size", json={"value": "500"}, headers=auth_headers)
        assert response.status_code == 400

    def test_cross_field_respects_a_prior_override(self, client, auth_headers, settings_override_path):
        # Lower max_page_size to 100 first.
        response = client.put("/settings/max_page_size", json={"value": "100"}, headers=auth_headers)
        assert response.status_code == 200
        # Now a default_page_size of 150 must be rejected against the *overridden* max, not the original 200 default.
        response = client.put("/settings/default_page_size", json={"value": "150"}, headers=auth_headers)
        assert response.status_code == 400

    def test_api_service_owned_setting_has_no_worker_busy_field(self, client, auth_headers, settings_override_path):
        response = client.put("/settings/jwt_expiry_minutes", json={"value": "720"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["restartGuidance"] == [
            {"owningService": "api-service", "restartCommand": "docker restart transactagent-api"}
        ]

    def test_shared_setting_returns_both_restart_targets(self, client, auth_headers, settings_override_path):
        response = client.put("/settings/gemini_model", json={"value": "gemini-4.0-flash"}, headers=auth_headers)
        assert response.status_code == 200
        services = {t["owningService"] for t in response.json()["restartGuidance"]}
        assert services == {"ingestion-worker", "api-service"}


class TestRestartGuidanceApi:
    def test_ingestion_worker_setting_reports_idle_when_nothing_running(
        self, client, auth_headers, settings_override_path
    ):
        response = client.get("/settings/similarity_threshold/restart-guidance", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()[0]["workerBusy"] is False

    def test_ingestion_worker_setting_reports_busy_when_a_run_is_active(
        self, client, auth_headers, settings_override_path, db_session, test_user
    ):
        from transactagent_db.models import IngestionRun, IngestionRunStatus

        db_session.add(IngestionRun(status=IngestionRunStatus.RUNNING, triggered_by_user_id=test_user.id))
        db_session.flush()

        response = client.get("/settings/similarity_threshold/restart-guidance", headers=auth_headers)
        assert response.json()[0]["workerBusy"] is True


class TestSettingHistoryApi:
    def test_empty_history_returns_empty_list(self, client, auth_headers, settings_override_path):
        response = client.get("/settings/history", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_history_reflects_changes_most_recent_first(self, client, auth_headers, settings_override_path, db_session):
        # Inserted directly with explicit, distinct changed_at values rather than via
        # two sequential PUT calls -- Postgres' NOW() is transaction-scoped (returns
        # the SAME value for the whole transaction, verified empirically), and this
        # test's client/db_session fixtures deliberately share one transaction across
        # requests, so two same-transaction PUTs would tie on changed_at. Explicit
        # timestamps here test the ORDER BY itself deterministically instead.
        from datetime import datetime, timedelta

        from transactagent_db.models import SettingChange, SettingOwningService

        base = datetime(2026, 8, 16, 9, 0, 0, tzinfo=UTC)
        db_session.add(
            SettingChange(
                setting_name="similarity_threshold",
                owning_service=SettingOwningService.INGESTION_WORKER,
                previous_value="85.0",
                new_value="90.0",
                changed_at=base,
            )
        )
        db_session.add(
            SettingChange(
                setting_name="similarity_threshold",
                owning_service=SettingOwningService.INGESTION_WORKER,
                previous_value="90.0",
                new_value="88.0",
                changed_at=base + timedelta(minutes=1),
            )
        )
        db_session.flush()

        response = client.get("/settings/history", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 2
        assert body[0]["newValue"] == "88.0"
        assert body[0]["previousValue"] == "90.0"
        assert body[1]["newValue"] == "90.0"
        assert body[1]["previousValue"] == "85.0"

    def test_history_survives_across_requests_not_just_in_memory(
        self, client, auth_headers, settings_override_path
    ):
        client.put("/settings/poll_interval_seconds", json={"value": "8.0"}, headers=auth_headers)
        first = client.get("/settings/history", headers=auth_headers).json()
        second = client.get("/settings/history", headers=auth_headers).json()
        assert first == second
