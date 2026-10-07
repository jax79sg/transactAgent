"""Issue #27: the guide cannot drift from the release number unnoticed."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guide  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

TEMPLATE = """<meta charset="utf-8">
<meta name="guide-version" content="{version}">
<title>Guide</title>
<div class="cover"><!--version-banner--><p>placeholder</p><!--/version-banner--></div>
<section id="dashboard"><h2>Dashboard</h2><p>The {version} text.</p></section>
"""


def write_repo(root: Path, version: str = "1.0.0", guide_version: str = None) -> None:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text(version + "\n")
    (root / "docs" / "index.html").write_text(TEMPLATE.format(version=guide_version or version))


@pytest.fixture
def repo(tmp_path):
    write_repo(tmp_path)
    return tmp_path


@pytest.fixture
def released(repo):
    guide.snapshot(repo, "First release", "2026-10-07")
    return repo


def release_next(root: Path, version: str, summary: str, date: str) -> None:
    write_repo(root, version)
    guide.snapshot(root, summary, date)


class TestTheRealRepository:
    def test_the_guide_matches_the_release_number_and_every_archive_is_in_order(self):
        assert guide.check(REPO_ROOT) == []


class TestSnapshot:
    def test_stores_an_archived_copy_with_its_own_banner_and_stamp(self, repo):
        guide.snapshot(repo, "First release", "2026-10-07")

        archive = (repo / "docs" / "v1.0.0" / "index.html").read_text()
        assert guide.banner("1.0.0", latest=False) in archive
        assert '<meta name="guide-version" content="1.0.0">' in archive
        assert "The 1.0.0 text." in archive

    def test_the_banners_link_to_the_right_places_from_where_each_page_lives(self, repo):
        guide.snapshot(repo, "First release", "2026-10-07")

        archive = (repo / "docs" / "v1.0.0" / "index.html").read_text()
        assert 'href="../"' in archive and 'href="../releases.html"' in archive  # one folder down
        latest = (repo / "docs" / "index.html").read_text()
        assert 'href="releases.html"' in latest and "../" not in guide.banner("1.0.0", latest=True)

    def test_the_latest_guide_gets_the_latest_banner(self, repo):
        guide.snapshot(repo, "First release", "2026-10-07")

        latest = (repo / "docs" / "index.html").read_text()
        assert guide.banner("1.0.0", latest=True) in latest
        assert "archived" not in latest

    def test_records_the_release_and_writes_the_index(self, repo):
        guide.snapshot(repo, "First release", "2026-10-07")

        assert json.loads((repo / "docs" / "releases.json").read_text()) == [
            {"version": "1.0.0", "date": "2026-10-07", "summary": "First release"}
        ]
        index = (repo / "docs" / "releases.html").read_text()
        assert 'href="v1.0.0/"' in index and "First release" in index and "2026-10-07" in index

    def test_a_snapshot_then_passes_the_check(self, repo):
        guide.snapshot(repo, "First release", "2026-10-07")

        assert guide.check(repo) == []

    def test_refuses_while_the_guide_is_still_for_another_version(self, repo):
        write_repo(repo, version="1.1.0", guide_version="1.0.0")

        with pytest.raises(ValueError, match="for version 1.0.0, not 1.1.0"):
            guide.snapshot(repo, "x", "2026-10-07")
        assert not (repo / "docs" / "v1.1.0").exists()

    def test_refuses_a_version_that_is_not_major_minor_patch(self, repo):
        (repo / "VERSION").write_text("v1\n")

        with pytest.raises(ValueError, match="not MAJOR.MINOR.PATCH"):
            guide.snapshot(repo, "x", "2026-10-07")

    def test_the_second_release_goes_first_and_leaves_the_first_archive_alone(self, released):
        before = (released / "docs" / "v1.0.0" / "index.html").read_text()

        release_next(released, "1.1.0", "Costs page", "2026-10-20")

        assert (released / "docs" / "v1.0.0" / "index.html").read_text() == before
        assert [r["version"] for r in json.loads((released / "docs" / "releases.json").read_text())] == ["1.1.0", "1.0.0"]
        assert guide.check(released) == []

    def test_the_index_marks_only_the_newest_as_latest(self, released):
        release_next(released, "1.1.0", "Costs page", "2026-10-20")

        index = (released / "docs" / "releases.html").read_text()
        tag = 'class="tag">latest'
        assert index.count(tag) == 1
        assert index.index("Version 1.1.0") < index.index(tag) < index.index("Version 1.0.0")

    def test_cutting_the_same_version_again_replaces_its_entry(self, released):
        guide.snapshot(released, "Reworded", "2026-10-08")

        assert json.loads((released / "docs" / "releases.json").read_text()) == [
            {"version": "1.0.0", "date": "2026-10-08", "summary": "Reworded"}
        ]
        assert guide.check(released) == []

    def test_orders_versions_numerically_not_alphabetically(self, released):
        release_next(released, "1.9.0", "nine", "2026-10-09")
        release_next(released, "1.10.0", "ten", "2026-10-10")

        assert [r["version"] for r in json.loads((released / "docs" / "releases.json").read_text())] == [
            "1.10.0", "1.9.0", "1.0.0",
        ]

    def test_a_summary_is_escaped_in_the_index(self, repo):
        guide.snapshot(repo, "Fix <script>alert(1)</script> & more", "2026-10-07")

        index = (repo / "docs" / "releases.html").read_text()
        assert "<script>" not in index
        assert "&lt;script&gt;" in index and "&amp; more" in index

    def test_a_guide_without_the_markers_is_refused_rather_than_half_written(self, repo):
        (repo / "docs" / "index.html").write_text('<meta name="guide-version" content="1.0.0"><p>no banner block</p>')

        with pytest.raises(ValueError, match="exactly one"):
            guide.snapshot(repo, "x", "2026-10-07")


class TestCheck:
    def test_a_fresh_repository_that_has_not_cut_its_release_is_told_so(self, repo):
        problems = guide.check(repo)

        assert any("no entry in docs/releases.json" in p for p in problems)
        assert any("not the latest-release banner" in p for p in problems)

    def test_missing_or_malformed_version(self, repo):
        (repo / "VERSION").write_text("one\n")
        assert guide.check(repo) == ["VERSION is 'one', not MAJOR.MINOR.PATCH"]
        (repo / "VERSION").unlink()
        assert guide.check(repo) == ["VERSION is missing"]

    def test_a_bumped_version_with_an_old_guide_names_both(self, released):
        (released / "VERSION").write_text("1.1.0\n")

        problems = guide.check(released)

        assert any("guide for version 1.0.0 but VERSION is 1.1.0" in p for p in problems)
        assert any("VERSION 1.1.0 has no entry" in p for p in problems)

    def test_a_bumped_version_with_an_updated_guide_still_needs_its_snapshot(self, released):
        write_repo(released, "1.1.0")

        problems = guide.check(released)

        assert problems and all("1.1.0" in p or "latest-release banner" in p for p in problems)
        assert any("has no entry" in p for p in problems)

    def test_the_latest_guide_missing_its_markers(self, released):
        (released / "docs" / "index.html").write_text("<p>nothing</p>")

        assert any("lacks the guide-version meta tag" in p for p in guide.check(released))

    def test_a_missing_latest_guide(self, released):
        (released / "docs" / "index.html").unlink()

        assert guide.check(released) == ["docs/index.html (the latest guide) is missing"]

    def test_a_missing_archive(self, released):
        (released / "docs" / "v1.0.0" / "index.html").unlink()

        assert any("no archived guide at docs/v1.0.0/index.html" in p for p in guide.check(released))

    def test_an_archive_stamped_for_another_version(self, released):
        archive = released / "docs" / "v1.0.0" / "index.html"
        archive.write_text(archive.read_text().replace('content="1.0.0"', 'content="0.9.0"'))

        assert any("not stamped as version 1.0.0" in p for p in guide.check(released))

    def test_an_archive_that_lost_its_banner(self, released):
        archive = released / "docs" / "v1.0.0" / "index.html"
        archive.write_text(archive.read_text().replace("archived guide for", "something else for"))

        assert any("lacks its archived-release banner" in p for p in guide.check(released))

    def test_an_archive_folder_nobody_listed(self, released):
        (released / "docs" / "v0.5.0").mkdir()
        (released / "docs" / "v0.5.0" / "index.html").write_text("old")

        assert any("docs/v0.5.0 is an archived guide that docs/releases.json does not list" in p for p in guide.check(released))

    @pytest.mark.parametrize("link", ['href="releases.html"', 'href="./"'])
    def test_an_archive_with_a_link_that_only_works_from_the_site_root(self, released, link):
        archive = released / "docs" / "v1.0.0" / "index.html"
        archive.write_text(archive.read_text() + "<p><a " + link + ">list</a></p>")

        problems = guide.check(released)

        assert any("goes nowhere" in p and "docs/v1.0.0/index.html" in p for p in problems)

    def test_a_link_that_works_from_either_place_is_fine_in_an_archive(self, released):
        archive = released / "docs" / "v1.0.0" / "index.html"
        archive.write_text(archive.read_text() + '<p><a href="https://example.org/releases.html">x</a> <a href="../">y</a></p>')

        assert guide.check(released) == []

    def test_a_stale_index(self, released):
        (released / "docs" / "releases.html").write_text("<p>old</p>")

        assert any("releases.html is out of date" in p for p in guide.check(released))

    def test_a_missing_index(self, released):
        (released / "docs" / "releases.html").unlink()

        assert "docs/releases.html is missing" in guide.check(released)

    def test_the_release_list_must_be_valid(self, released):
        path = released / "docs" / "releases.json"
        path.write_text("not json")
        assert any("cannot be read" in p for p in guide.check(released))

        path.write_text(json.dumps([{"version": "1.x", "date": "d", "summary": "s"}]))
        assert any("without a MAJOR.MINOR.PATCH version" in p for p in guide.check(released))

    def test_duplicates_ordering_and_blank_fields_are_reported(self, released):
        entry = {"version": "1.0.0", "date": "2026-10-07", "summary": "First release"}
        path = released / "docs" / "releases.json"

        path.write_text(json.dumps([entry, entry]))
        assert any("lists a version twice" in p for p in guide.check(released))

        path.write_text(json.dumps([entry, {"version": "1.1.0", "date": "d", "summary": "s"}]))
        assert any("not ordered newest first" in p for p in guide.check(released))

        path.write_text(json.dumps([{"version": "1.0.0", "date": "", "summary": ""}]))
        problems = guide.check(released)
        assert any("has no date" in p for p in problems) and any("has no summary" in p for p in problems)

    def test_a_version_older_than_the_newest_release_is_flagged(self, released):
        release_next(released, "1.1.0", "Next", "2026-10-20")
        (released / "VERSION").write_text("1.0.0\n")

        assert any("is not the newest release" in p for p in guide.check(released))


class TestCommandLine:
    def test_check_prints_ok_and_exits_zero(self, released, capsys):
        assert guide.main(["check"], root=released) == 0
        assert "guide check: ok (version 1.0.0)" in capsys.readouterr().out

    def test_check_prints_each_problem_and_exits_one(self, released, capsys):
        (released / "VERSION").write_text("1.1.0\n")

        assert guide.main(["check"], root=released) == 1
        out = capsys.readouterr().out
        assert out.count("guide check:") >= 2 and "ok" not in out

    def test_snapshot_reports_what_it_cut(self, repo, capsys):
        assert guide.main(["snapshot", "--summary", "First", "--date", "2026-10-07"], root=repo) == 0
        assert "cut version 1.0.0" in capsys.readouterr().out

    def test_snapshot_failure_exits_one_with_the_reason(self, repo, capsys):
        write_repo(repo, "1.1.0", guide_version="1.0.0")

        assert guide.main(["snapshot", "--summary", "x"], root=repo) == 1
        assert "update the guide for this release first" in capsys.readouterr().out

    def test_snapshot_needs_a_summary(self, repo):
        with pytest.raises(SystemExit):
            guide.main(["snapshot"], root=repo)


def test_version_ordering_is_numeric():
    assert guide.version_key("1.10.0") > guide.version_key("1.9.0") > guide.version_key("1.0.0")
