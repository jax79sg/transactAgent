"""Issue #27: GET /version tells the interface which release the server is on, without a login."""

from pathlib import Path

from transactagent_db import version as version_module
from transactagent_db.version import UNKNOWN_VERSION

REPO_VERSION = (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()


class TestVersionEndpoint:
    def test_it_answers_without_a_login_with_the_release_in_the_version_file(self, client):
        response = client.get("/version")

        assert response.status_code == 200
        assert response.json() == {"version": REPO_VERSION}

    def test_it_follows_the_file(self, client, tmp_path, monkeypatch):
        path = tmp_path / "VERSION"
        path.write_text("3.2.1\n")
        monkeypatch.setattr(version_module, "_VERSION_FILE", path)

        assert client.get("/version").json() == {"version": "3.2.1"}

    def test_a_missing_file_is_reported_as_unknown_not_a_server_error(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(version_module, "_VERSION_FILE", tmp_path / "gone")

        response = client.get("/version")

        assert response.status_code == 200
        assert response.json() == {"version": UNKNOWN_VERSION}

    def test_the_health_check_is_unchanged(self, client):
        assert client.get("/health").json() == {"status": "ok"}
