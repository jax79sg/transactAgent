"""Issue #27: the one release number, read from the VERSION file at the repository root."""

from pathlib import Path

import pytest

from transactagent_db import version as version_module
from transactagent_db.version import SEMVER, UNKNOWN_VERSION, app_version

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestAppVersion:
    def test_the_repositorys_own_version_file_is_read_and_is_a_release_number(self):
        assert SEMVER.match(app_version())
        assert app_version() == (REPO_ROOT / "VERSION").read_text().strip()

    def test_the_default_location_is_the_file_at_the_repository_root(self):
        """The images put VERSION at /app, three folders above this package, exactly as in a checkout."""
        assert version_module._VERSION_FILE == REPO_ROOT / "VERSION"

    @pytest.mark.parametrize("text", ["1.0.0", "1.0.0\n", "  2.13.4  \n", "0.0.0", "10.20.30"])
    def test_a_release_number_is_returned_without_its_whitespace(self, tmp_path, text):
        path = tmp_path / "VERSION"
        path.write_text(text)

        assert app_version(path) == text.strip()

    @pytest.mark.parametrize("text", ["", "\n", "1.0", "1", "v1.0.0", "1.0.0-beta", "1.0.0.0", "one.two.three", "1.0.0 and more"])
    def test_anything_that_is_not_major_minor_patch_is_unknown(self, tmp_path, text):
        path = tmp_path / "VERSION"
        path.write_text(text)

        assert app_version(path) == UNKNOWN_VERSION

    def test_a_missing_file_is_unknown_not_an_error(self, tmp_path):
        assert app_version(tmp_path / "does-not-exist") == UNKNOWN_VERSION

    def test_the_default_file_is_looked_up_when_called_so_it_can_be_pointed_elsewhere(self, tmp_path, monkeypatch):
        path = tmp_path / "VERSION"
        path.write_text("7.8.9\n")
        monkeypatch.setattr(version_module, "_VERSION_FILE", path)

        assert app_version() == "7.8.9"
