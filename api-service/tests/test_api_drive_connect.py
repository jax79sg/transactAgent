class TestDriveConnectApi:
    def test_status_reports_not_connected_initially(self, client, auth_headers):
        response = client.get("/drive/status", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["connected"] is False

    def test_status_requires_auth(self, client):
        response = client.get("/drive/status")
        assert response.status_code == 401

    def test_connect_requires_auth(self, client):
        response = client.get("/drive/connect")
        assert response.status_code == 401

    def test_connect_returns_google_authorization_url(self, client, auth_headers):
        response = client.get("/drive/connect", headers=auth_headers)
        assert response.status_code == 200
        url = response.json()["authorizationUrl"]
        assert url.startswith("https://accounts.google.com/o/oauth2/")

    def test_callback_with_unknown_state_is_rejected(self, client):
        response = client.get(
            "/drive/callback", params={"code": "fake-code", "state": "never-issued"}, follow_redirects=False
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_oauth_state"


class TestDriveStatusTellsTheTruth:
    """Issues #65-#70 (#70): a saved credential that Google has revoked or expired used to read as "Connected", while
    every ingestion download and the nightly backup failed with invalid_grant. The status now asks Google."""

    @staticmethod
    def _saved_credential(db_session):
        from api_service.drive_connect import repository

        repository.upsert_credential(db_session, refresh_token="saved-refresh-token", access_token=None, access_token_expires_at=None)

    @staticmethod
    def _google_answers(monkeypatch, behaviour):
        """Stand in for google.oauth2.credentials.Credentials: `behaviour` is an exception to raise on refresh, or None."""
        from api_service.drive_connect import service

        class FakeCredentials:
            def __init__(self, **_kwargs):
                pass

            def refresh(self, _request):
                if behaviour is not None:
                    raise behaviour

        monkeypatch.setattr(service, "Credentials", FakeCredentials)

    def test_nothing_saved_is_not_connected_and_needs_no_reconnect(self, client, auth_headers):
        body = client.get("/drive/status", headers=auth_headers).json()
        assert body == {"connected": False, "needsReconnect": False}

    def test_a_credential_google_still_accepts_is_connected(self, client, auth_headers, db_session, monkeypatch):
        self._saved_credential(db_session)
        self._google_answers(monkeypatch, None)

        body = client.get("/drive/status", headers=auth_headers).json()

        assert body == {"connected": True, "needsReconnect": False}

    def test_a_credential_google_refuses_needs_a_reconnect(self, client, auth_headers, db_session, monkeypatch):
        from google.auth.exceptions import RefreshError

        self._saved_credential(db_session)
        self._google_answers(monkeypatch, RefreshError("invalid_grant: Bad Request"))

        body = client.get("/drive/status", headers=auth_headers).json()

        assert body == {"connected": True, "needsReconnect": True}

    def test_no_network_is_not_reported_as_a_broken_credential(self, client, auth_headers, db_session, monkeypatch):
        from google.auth.exceptions import TransportError

        self._saved_credential(db_session)
        self._google_answers(monkeypatch, TransportError("connection refused"))

        body = client.get("/drive/status", headers=auth_headers).json()

        assert body == {"connected": True, "needsReconnect": False}

    def test_an_unexpected_failure_is_not_reported_as_a_broken_credential(self, client, auth_headers, db_session, monkeypatch):
        self._saved_credential(db_session)
        self._google_answers(monkeypatch, RuntimeError("something else"))

        body = client.get("/drive/status", headers=auth_headers).json()

        assert body == {"connected": True, "needsReconnect": False}
