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
