class TestHealthEndpoint:
    def test_health_requires_no_auth_and_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
