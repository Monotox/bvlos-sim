"""Tests for version bump and release tooling (Ticket 098)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import app
from bvlos_sim.adapters.release import (
    BumpPart,
    ReleaseError,
    apply_bump,
    bump_version,
    check_consistency,
    parse_version,
    plan_bump,
    read_pyproject_version,
    roll_changelog,
    set_pyproject_version,
)
from bvlos_sim.adapters.version import resolved_package_version, tool_version

runner = CliRunner()

_PYPROJECT = '[project]\nname = "bvlos-sim"\nversion = "0.32.0"\nreadme = "README.md"\n'
_CHANGELOG = (
    "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- a thing\n\n"
    "## [0.32.0] - 2026-05-29\n\n### Added\n\n- older thing\n"
)


# ---------------------------------------------------------------------------
# Semver arithmetic
# ---------------------------------------------------------------------------


def test_bump_patch() -> None:
    assert bump_version("0.32.0", BumpPart.PATCH) == "0.32.1"


def test_bump_minor_resets_patch() -> None:
    assert bump_version("0.32.4", BumpPart.MINOR) == "0.33.0"


def test_bump_major_resets_minor_and_patch() -> None:
    assert bump_version("1.4.9", BumpPart.MAJOR) == "2.0.0"


def test_parse_version_rejects_non_semver() -> None:
    with pytest.raises(ReleaseError):
        parse_version("0.32")


def test_parse_version_rejects_suffix() -> None:
    with pytest.raises(ReleaseError):
        parse_version("0.32.0-rc1")


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def test_read_pyproject_version() -> None:
    assert read_pyproject_version(_PYPROJECT) == "0.32.0"


def test_set_pyproject_version_replaces_only_project_version() -> None:
    updated = set_pyproject_version(_PYPROJECT, "0.33.0")
    assert 'version = "0.33.0"' in updated
    assert 'name = "bvlos-sim"' in updated
    assert read_pyproject_version(updated) == "0.33.0"


def test_read_pyproject_version_missing_raises() -> None:
    with pytest.raises(ReleaseError):
        read_pyproject_version('[project]\nname = "x"\n')


# ---------------------------------------------------------------------------
# CHANGELOG roll
# ---------------------------------------------------------------------------


def test_roll_changelog_inserts_dated_section_and_fresh_unreleased() -> None:
    rolled = roll_changelog(_CHANGELOG, "0.33.0", "2026-06-01")
    assert "## [Unreleased]\n\n## [0.33.0] - 2026-06-01" in rolled
    # The previous release is preserved.
    assert "## [0.32.0] - 2026-05-29" in rolled
    # The unreleased entry now lives under the new dated section.
    assert rolled.index("0.33.0") < rolled.index("- a thing")


def test_roll_changelog_without_unreleased_raises() -> None:
    with pytest.raises(ReleaseError):
        roll_changelog(
            "# Changelog\n\n## [0.1.0] - 2020-01-01\n", "0.2.0", "2026-06-01"
        )


def test_roll_changelog_only_rolls_first_unreleased() -> None:
    rolled = roll_changelog(_CHANGELOG, "0.33.0", "2026-06-01")
    assert rolled.count("## [Unreleased]") == 1


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------


def test_check_consistency_flags_pyproject_behind_tag() -> None:
    problems = check_consistency("0.30.0", "v0.31.0")
    assert problems
    assert "behind" in problems[0]


def test_check_consistency_ok_when_equal() -> None:
    assert check_consistency("0.32.0", "v0.32.0") == []


def test_check_consistency_ok_when_ahead() -> None:
    assert check_consistency("0.33.0", "v0.32.0") == []


def test_check_consistency_ok_without_tags() -> None:
    assert check_consistency("0.32.0", None) == []


def test_check_consistency_flags_malformed_tag() -> None:
    problems = check_consistency("0.32.0", "release-1")
    assert problems


# ---------------------------------------------------------------------------
# Filesystem orchestration
# ---------------------------------------------------------------------------


def _write_fixtures(tmp_path: Path) -> tuple[Path, Path]:
    pyproject = tmp_path / "pyproject.toml"
    changelog = tmp_path / "CHANGELOG.md"
    pyproject.write_text(_PYPROJECT, encoding="utf-8")
    changelog.write_text(_CHANGELOG, encoding="utf-8")
    return pyproject, changelog


def test_plan_bump_does_not_write(tmp_path: Path) -> None:
    pyproject, changelog = _write_fixtures(tmp_path)
    current, nxt, new_pyproject, new_changelog = plan_bump(
        part=BumpPart.MINOR,
        pyproject_path=pyproject,
        changelog_path=changelog,
        today="2026-06-01",
    )
    assert (current, nxt) == ("0.32.0", "0.33.0")
    assert 'version = "0.33.0"' in new_pyproject
    assert "## [0.33.0] - 2026-06-01" in new_changelog
    # Files on disk are unchanged.
    assert pyproject.read_text(encoding="utf-8") == _PYPROJECT
    assert changelog.read_text(encoding="utf-8") == _CHANGELOG


def test_apply_bump_writes_both_files(tmp_path: Path) -> None:
    pyproject, changelog = _write_fixtures(tmp_path)
    current, nxt = apply_bump(
        part=BumpPart.PATCH,
        pyproject_path=pyproject,
        changelog_path=changelog,
        today="2026-06-01",
    )
    assert (current, nxt) == ("0.32.0", "0.32.1")
    assert read_pyproject_version(pyproject.read_text(encoding="utf-8")) == "0.32.1"
    assert "## [0.32.1] - 2026-06-01" in changelog.read_text(encoding="utf-8")


def test_apply_bump_rolls_back_when_second_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import bvlos_sim.adapters.release as release_module

    pyproject, changelog = _write_fixtures(tmp_path)
    real_write = release_module.atomic_write_text
    call_count = 0

    def fail_second_write(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("synthetic changelog failure")
        real_write(path, text, encoding=encoding)

    monkeypatch.setattr(release_module, "atomic_write_text", fail_second_write)

    with pytest.raises(OSError, match="synthetic changelog failure"):
        apply_bump(
            part=BumpPart.PATCH,
            pyproject_path=pyproject,
            changelog_path=changelog,
            today="2026-06-01",
        )

    assert pyproject.read_text(encoding="utf-8") == _PYPROJECT
    assert changelog.read_text(encoding="utf-8") == _CHANGELOG


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_reports_without_writing() -> None:
    result = runner.invoke(app, ["bump", "patch", "--dry-run"])
    assert result.exit_code == 0
    assert "Would bump" in result.output
    assert "No files modified" in result.output


def test_cli_check_reports_sources() -> None:
    result = runner.invoke(app, ["bump", "--check"])
    assert result.exit_code in (0, 11)
    assert "pyproject.toml:" in result.output
    assert "latest git tag:" in result.output


def test_cli_no_part_without_check_errors() -> None:
    result = runner.invoke(app, ["bump"])
    assert result.exit_code == 11
    assert "major, minor, or patch" in result.output


# ---------------------------------------------------------------------------
# Version-agnostic fixtures (strategy B)
# ---------------------------------------------------------------------------


def test_tool_version_is_pinned_placeholder_under_tests() -> None:
    # conftest.py pins the embedded version so golden fixtures never churn on a bump.
    assert tool_version() == "0.0.0-test"


def test_resolved_package_version_is_real_semver() -> None:
    # The live version is asserted here, separately from the fixtures.
    parse_version(resolved_package_version())


__all__: list[str] = []
