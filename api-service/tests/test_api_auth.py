class TestLoginEndpoint:
    def test_correct_credentials_return_token(self, client, test_user):
        response = client.post(
            "/auth/login", json={"username": "account_owner", "password": "correct horse battery staple"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("token")
        assert "expiresAt" in body

    def test_wrong_password_returns_401(self, client, test_user):
        response = client.post("/auth/login", json={"username": "account_owner", "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"

    def test_unknown_username_returns_401(self, client):
        response = client.post("/auth/login", json={"username": "nobody", "password": "whatever"})
        assert response.status_code == 401


class TestAuthenticationRequired:
    """AR-1: every route except /auth/login and /health requires a valid JWT."""

    def test_protected_route_without_token_returns_401(self, client):
        response = client.get("/categories")
        assert response.status_code == 401

    def test_protected_route_with_invalid_token_returns_401(self, client):
        response = client.get("/categories", headers={"Authorization": "Bearer not-a-real-token"})
        assert response.status_code == 401

    def test_protected_route_with_valid_token_succeeds(self, client, auth_headers):
        response = client.get("/categories", headers=auth_headers)
        assert response.status_code == 200
