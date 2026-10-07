#!/usr/bin/env python3
"""Keeps the user guide in step with the release number (issue #27).

    python scripts/guide.py check
        Fails (exit 1, one line per problem) when VERSION, the latest guide, the archived copies and the releases
        index disagree. Run by CI on every pull request.

    python scripts/guide.py snapshot --summary "What changed" [--date 2026-10-07]
        Cuts the release in VERSION: stores a copy of the guide as docs/v<VERSION>/index.html, records the release in
        docs/releases.json and rewrites docs/releases.html. The latest guide (docs/index.html) must already be
        updated for this release and say so (its <meta name="guide-version">).

Only the standard library, and syntax from Python 3.9 on, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
META = re.compile(r'<meta name="guide-version" content="([^"]*)">')
BANNER = re.compile(r"<!--version-banner-->.*?<!--/version-banner-->", re.DOTALL)
ARCHIVED_BANNER = re.compile(r'class="version-banner archived"')
# Links that are right in the latest guide (at the site root) but break in an archived copy one folder down.
ROOT_RELATIVE_LINKS = ('href="releases.html"', 'href="./"')

REPO_ROOT = Path(__file__).resolve().parents[1]


def version_key(version: str):
    return tuple(int(part) for part in version.split("."))


def banner(version: str, latest: bool) -> str:
    if latest:
        body = (
            '<p class="version-banner">Guide for <strong>version {v}</strong>, the latest release. '
            '<a href="releases.html">All versions</a></p>'
        ).format(v=version)
    else:
        body = (
            '<p class="version-banner archived">This is the archived guide for <strong>version {v}</strong>. '
            '<a href="../">Read the latest guide</a> &middot; <a href="../releases.html">All versions</a></p>'
        ).format(v=version)
    return "<!--version-banner-->" + body + "<!--/version-banner-->"


def with_version(guide: str, version: str, latest: bool) -> str:
    """The guide's text stamped for `version`: its meta tag and its banner (latest or archived)."""
    guide, meta_count = META.subn('<meta name="guide-version" content="{}">'.format(version), guide)
    guide, banner_count = BANNER.subn(lambda _m: banner(version, latest), guide)
    if meta_count != 1 or banner_count != 1:
        raise ValueError("the guide must contain exactly one guide-version meta tag and one version-banner block")
    return guide


def read_version(root: Path) -> str:
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def load_releases(root: Path) -> List[dict]:
    path = root / "docs" / "releases.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def releases_html(releases: List[dict]) -> str:
    """The index of every release's guide, newest first; the first one is also the latest guide."""
    rows = []
    for position, release in enumerate(releases):
        version = release["version"]
        latest = ' <span class="tag">latest</span>' if position == 0 else ""
        rows.append(
            '    <li><a href="v{v}/">Version {v}</a>{latest}'
            '<span class="date">{date}</span><span class="what">{what}</span></li>'.format(
                v=version, latest=latest, date=html.escape(release["date"]), what=html.escape(release["summary"])
            )
        )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Bank Transaction Insights — Guide releases</title>\n"
        "<style>\n"
        "  :root { color-scheme: light dark; --ink: #1b2130; --muted: #5b6472; --accent: #1e6b63; --border: #e1e4ea; }\n"
        "  @media (prefers-color-scheme: dark) { :root { --ink: #e7eaf0; --muted: #9aa3b2; --accent: #59c9b9; --border: #2a303c; } }\n"
        "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 44rem; "
        "margin: 2rem auto; padding: 0 1rem; color: var(--ink); line-height: 1.5; }\n"
        "  a { color: var(--accent); }\n"
        "  ul { list-style: none; padding: 0; }\n"
        "  li { border-top: 1px solid var(--border); padding: .75rem 0; }\n"
        "  .date { color: var(--muted); margin-left: .75rem; font-size: .9rem; }\n"
        "  .what { display: block; color: var(--muted); }\n"
        "  .tag { font-size: .75rem; border: 1px solid var(--accent); color: var(--accent); border-radius: 999px; "
        "padding: 0 .5rem; margin-left: .5rem; }\n"
        "</style>\n</head>\n<body>\n"
        "<h1>Guide releases</h1>\n"
        '<p>Every release of Bank Transaction Insights keeps its own copy of the user guide. The version of the app you are '
        "running is shown in its top bar and on the Settings page. <a href=\"./\">Read the latest guide</a>.</p>\n"
        "<ul>\n" + "\n".join(rows) + "\n</ul>\n</body>\n</html>\n"
    )


def check(root: Path) -> List[str]:
    problems: List[str] = []
    version_file = root / "VERSION"
    if not version_file.exists():
        return ["VERSION is missing"]
    version = read_version(root)
    if not SEMVER.match(version):
        return ["VERSION is {!r}, not MAJOR.MINOR.PATCH".format(version)]

    guide_path = root / "docs" / "index.html"
    if not guide_path.exists():
        return ["docs/index.html (the latest guide) is missing"]
    guide = guide_path.read_text(encoding="utf-8")
    meta = META.search(guide)
    if meta is None or not BANNER.search(guide):
        problems.append("docs/index.html lacks the guide-version meta tag or the version-banner block")
    elif meta.group(1) != version:
        problems.append(
            "docs/index.html is the guide for version {} but VERSION is {}: update the guide for this release, "
            "then run `python scripts/guide.py snapshot`".format(meta.group(1), version)
        )
    elif banner(version, True) not in guide:
        problems.append("docs/index.html's version banner is not the latest-release banner for version " + version)

    try:
        releases = load_releases(root)
    except (ValueError, OSError) as exc:
        return problems + ["docs/releases.json cannot be read: {}".format(exc)]
    versions = [r.get("version") for r in releases]
    if any(not isinstance(v, str) or not SEMVER.match(v) for v in versions):
        return problems + ["docs/releases.json has an entry without a MAJOR.MINOR.PATCH version"]
    if len(set(versions)) != len(versions):
        problems.append("docs/releases.json lists a version twice")
    if versions != sorted(versions, key=version_key, reverse=True):
        problems.append("docs/releases.json is not ordered newest first")
    if version not in versions:
        problems.append(
            "VERSION {} has no entry in docs/releases.json: run `python scripts/guide.py snapshot --summary ...`".format(version)
        )
    elif versions[0] != version:
        problems.append("VERSION {} is not the newest release in docs/releases.json ({})".format(version, versions[0]))

    for release in releases:
        for field in ("date", "summary"):
            if not release.get(field):
                problems.append("release {} has no {}".format(release["version"], field))
        archive = root / "docs" / ("v" + release["version"]) / "index.html"
        if not archive.exists():
            problems.append("release {} has no archived guide at docs/v{}/index.html".format(release["version"], release["version"]))
            continue
        text = archive.read_text(encoding="utf-8")
        found = META.search(text)
        if found is None or found.group(1) != release["version"]:
            problems.append("docs/v{}/index.html is not stamped as version {}".format(release["version"], release["version"]))
        elif banner(release["version"], False) not in text:
            problems.append("docs/v{}/index.html lacks its archived-release banner".format(release["version"]))
        for link in ROOT_RELATIVE_LINKS:
            if link in text:
                problems.append(
                    "docs/v{v}/index.html has {link}, which resolves inside docs/v{v}/ and goes nowhere; "
                    "use the full address (https://jax79sg.github.io/transactAgent/...) or ../".format(v=release["version"], link=link)
                )

    docs = root / "docs"
    for folder in sorted(docs.glob("v*")):
        if folder.is_dir() and folder.name[1:] not in versions:
            problems.append("docs/{} is an archived guide that docs/releases.json does not list".format(folder.name))

    index_path = docs / "releases.html"
    if not index_path.exists():
        problems.append("docs/releases.html is missing")
    elif index_path.read_text(encoding="utf-8") != releases_html(releases):
        problems.append("docs/releases.html is out of date with docs/releases.json: run `python scripts/guide.py snapshot`")
    return problems


def snapshot(root: Path, summary: str, date: Optional[str] = None) -> str:
    version = read_version(root)
    if not SEMVER.match(version):
        raise ValueError("VERSION is {!r}, not MAJOR.MINOR.PATCH".format(version))
    guide_path = root / "docs" / "index.html"
    guide = guide_path.read_text(encoding="utf-8")
    meta = META.search(guide)
    if meta is None or meta.group(1) != version:
        raise ValueError(
            "docs/index.html is for version {}, not {}: update the guide for this release first".format(
                meta.group(1) if meta else "(none)", version
            )
        )
    guide_path.write_text(with_version(guide, version, latest=True), encoding="utf-8")

    archive = root / "docs" / ("v" + version) / "index.html"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(with_version(guide, version, latest=False), encoding="utf-8")

    releases = [r for r in load_releases(root) if r["version"] != version]
    releases.append({"version": version, "date": date or datetime.date.today().isoformat(), "summary": summary})
    releases.sort(key=lambda r: version_key(r["version"]), reverse=True)
    (root / "docs" / "releases.json").write_text(json.dumps(releases, indent=2) + "\n", encoding="utf-8")
    (root / "docs" / "releases.html").write_text(releases_html(releases), encoding="utf-8")
    return version


def main(argv: Optional[List[str]] = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--summary", required=True, help="one line on what this release adds")
    snap.add_argument("--date", help="release date, YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    if args.command == "check":
        problems = check(root)
        for problem in problems:
            print("guide check: " + problem)
        if not problems:
            print("guide check: ok (version {})".format(read_version(root)))
        return 1 if problems else 0

    try:
        version = snapshot(root, args.summary, args.date)
    except ValueError as exc:
        print("guide snapshot: " + str(exc))
        return 1
    print("guide snapshot: cut version {} (docs/v{}/index.html, docs/releases.json, docs/releases.html)".format(version, version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
