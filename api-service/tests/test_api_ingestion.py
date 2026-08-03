class TestIngestionApi:
    def test_start_run_returns_202(self, client, auth_headers):
        response = client.post("/ingestion/runs", headers=auth_headers)
        assert response.status_code == 202
        assert response.json()["runId"]

    def test_start_run_while_active_returns_409(self, client, auth_headers):
        first = client.post("/ingestion/runs", headers=auth_headers)
        assert first.status_code == 202

        second = client.post("/ingestion/runs", headers=auth_headers)
        assert second.status_code == 409
        assert second.json()["error"] == "ingestion_run_already_active"

    def test_get_unknown_run_returns_404(self, client, auth_headers):
        import uuid

        response = client.get(f"/ingestion/runs/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404


class TestIngestionRunLogsApi:
    def _start_run(self, client, auth_headers):
        return client.post("/ingestion/runs", headers=auth_headers).json()["runId"]

    def _add_log(self, db_session, run_id, message, level="INFO"):
        from transactagent_db.models import IngestionRunLog

        log = IngestionRunLog(ingestion_run_id=run_id, level=level, logger_name="ingestion_worker.test", message=message)
        db_session.add(log)
        db_session.flush()
        return log

    def test_logs_requires_auth(self, client):
        import uuid

        response = client.get(f"/ingestion/runs/{uuid.uuid4()}/logs")
        assert response.status_code == 401

    def test_unknown_run_returns_404(self, client, auth_headers):
        import uuid

        response = client.get(f"/ingestion/runs/{uuid.uuid4()}/logs", headers=auth_headers)
        assert response.status_code == 404

    def test_returns_logs_in_order(self, client, auth_headers, db_session):
        run_id = self._start_run(client, auth_headers)
        self._add_log(db_session, run_id, "Starting run")
        self._add_log(db_session, run_id, "Found 2 files")

        response = client.get(f"/ingestion/runs/{run_id}/logs", headers=auth_headers)
        assert response.status_code == 200
        messages = [line["message"] for line in response.json()]
        assert messages == ["Starting run", "Found 2 files"]

    def test_after_id_returns_only_newer_lines(self, client, auth_headers, db_session):
        run_id = self._start_run(client, auth_headers)
        first = self._add_log(db_session, run_id, "Starting run")
        self._add_log(db_session, run_id, "Found 2 files")

        response = client.get(f"/ingestion/runs/{run_id}/logs", headers=auth_headers, params={"after_id": first.id})
        assert response.status_code == 200
        messages = [line["message"] for line in response.json()]
        assert messages == ["Found 2 files"]

    def test_logs_from_a_different_run_are_not_included(self, client, auth_headers, db_session, test_user):
        from transactagent_db.models import IngestionRun, IngestionRunStatus

        run_id = self._start_run(client, auth_headers)
        self._add_log(db_session, run_id, "This run's log")

        # ingestion_run_id is a real foreign key -- a second run must actually exist to
        # attach a log to it. Given directly (not via POST /ingestion/runs), since only
        # one queued/running run is allowed at a time and one is already active.
        other_run = IngestionRun(triggered_by_user_id=test_user.id, status=IngestionRunStatus.COMPLETED)
        db_session.add(other_run)
        db_session.flush()
        self._add_log(db_session, other_run.id, "Some other run's log")

        response = client.get(f"/ingestion/runs/{run_id}/logs", headers=auth_headers)
        assert response.status_code == 200
        messages = [line["message"] for line in response.json()]
        assert messages == ["This run's log"]
