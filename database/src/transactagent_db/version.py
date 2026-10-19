"""The app's release number: one source (the VERSION file at the repository root) read by every service, the
frontend's build and the guide's release check (issue #27).

In the images the file sits at /app/VERSION, which is exactly three levels above this module's folder
(`<root>/database/src/transactagent_db/`), the same as in a source checkout, so one lookup serves both.
"""

import re
from pathlib import Path

UNKNOWN_VERSION = "unknown"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

_VERSION_FILE = Path(__file__).resolve().parents[3] / "VERSION"


def app_version(version_file: Path | None = None) -> str:
    """The release number, or "unknown" when the file is missing or is not MAJOR.MINOR.PATCH. Never raises: a
    service must start whether or not someone remembered to ship the file."""
    try:
        text = (version_file or _VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return UNKNOWN_VERSION
    return text if SEMVER.match(text) else UNKNOWN_VERSION
