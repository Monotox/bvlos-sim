"""Release tooling: semver bump, changelog roll, and version-consistency checks.

Pure, side-effect-light helpers shared by the ``bump`` CLI command and its tests.
Git and filesystem access is isolated in small functions so the arithmetic and
text transforms can be unit-tested directly.
"""

from __future__ import annotations

import re
import subprocess
from datetime import date
from enum import StrEnum
from pathlib import Path

from adapters.atomic_write import atomic_write_text

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PYPROJECT_VERSION_RE = re.compile(r'^version = "(\d+\.\d+\.\d+)"$', re.MULTILINE)
_UNRELEASED_HEADING = "## [Unreleased]"

REPO_ROOT = Path(__file__).resolve().parent.parent


class BumpPart(StrEnum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


class ReleaseError(ValueError):
    """Raised when a version string, changelog, or repository state is invalid."""


# ---------------------------------------------------------------------------
# Semver arithmetic
# ---------------------------------------------------------------------------


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse ``MAJOR.MINOR.PATCH`` into a tuple, raising ReleaseError if malformed."""
    match = _SEMVER_RE.match(version)
    if match is None:
        raise ReleaseError(f"Not a MAJOR.MINOR.PATCH version: {version!r}")
    return int(match[1]), int(match[2]), int(match[3])


def bump_version(version: str, part: BumpPart) -> str:
    """Return the next version after bumping ``part``, resetting lower components."""
    major, minor, patch = parse_version(version)
    if part is BumpPart.MAJOR:
        return f"{major + 1}.0.0"
    if part is BumpPart.MINOR:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def read_pyproject_version(pyproject_text: str) -> str:
    """Extract the ``[project].version`` value from pyproject text."""
    match = _PYPROJECT_VERSION_RE.search(pyproject_text)
    if match is None:
        raise ReleaseError('No `version = "X.Y.Z"` line found in pyproject.toml.')
    return match[1]


def set_pyproject_version(pyproject_text: str, new_version: str) -> str:
    """Return pyproject text with the project version replaced by ``new_version``."""
    parse_version(new_version)  # validate
    new_text, count = _PYPROJECT_VERSION_RE.subn(
        f'version = "{new_version}"', pyproject_text, count=1
    )
    if count != 1:
        raise ReleaseError('No `version = "X.Y.Z"` line found in pyproject.toml.')
    return new_text


# ---------------------------------------------------------------------------
# CHANGELOG.md
# ---------------------------------------------------------------------------


def roll_changelog(changelog_text: str, new_version: str, today: str) -> str:
    """Rename ``## [Unreleased]`` to ``## [X.Y.Z] - <today>`` and add a fresh Unreleased.

    Raises ReleaseError if no Unreleased section is present.
    """
    if _UNRELEASED_HEADING not in changelog_text:
        raise ReleaseError("CHANGELOG.md has no '## [Unreleased]' section to roll.")
    replacement = f"{_UNRELEASED_HEADING}\n\n## [{new_version}] - {today}"
    return changelog_text.replace(_UNRELEASED_HEADING, replacement, 1)


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def latest_git_tag(repo_root: Path = REPO_ROOT) -> str | None:
    """Return the highest semver ``v*`` git tag, or None if there are none / no git."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "tag", "--list", "v*", "--sort=-v:refname"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in result.stdout.splitlines():
        tag = line.strip()
        if tag:
            return tag
    return None


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------


def check_consistency(pyproject_version: str, latest_tag: str | None) -> list[str]:
    """Return human-readable drift problems between pyproject and the latest tag.

    An empty list means consistent. The invariant is that the working version is
    never *behind* the latest released tag (the drift seen before v0.32.0, where
    pyproject was 0.30.0 while the tag was already v0.31.0).
    """
    problems: list[str] = []
    project = parse_version(pyproject_version)
    if latest_tag is None:
        return problems
    tag_version = latest_tag[1:] if latest_tag.startswith("v") else latest_tag
    try:
        tag = parse_version(tag_version)
    except ReleaseError:
        problems.append(
            f"Latest git tag {latest_tag!r} is not a vMAJOR.MINOR.PATCH tag."
        )
        return problems
    if project < tag:
        problems.append(
            f"pyproject.toml version {pyproject_version} is behind the latest git "
            f"tag {latest_tag} (working version must be >= the released version)."
        )
    return problems


# ---------------------------------------------------------------------------
# Orchestration (filesystem)
# ---------------------------------------------------------------------------


def today_iso() -> str:
    return date.today().isoformat()


def plan_bump(
    *,
    part: BumpPart,
    pyproject_path: Path,
    changelog_path: Path,
    today: str | None = None,
) -> tuple[str, str, str, str]:
    """Compute the bump without writing anything.

    Returns (current_version, next_version, new_pyproject_text, new_changelog_text).
    """
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    changelog_text = changelog_path.read_text(encoding="utf-8")
    current = read_pyproject_version(pyproject_text)
    nxt = bump_version(current, part)
    new_pyproject = set_pyproject_version(pyproject_text, nxt)
    new_changelog = roll_changelog(changelog_text, nxt, today or today_iso())
    return current, nxt, new_pyproject, new_changelog


def apply_bump(
    *,
    part: BumpPart,
    pyproject_path: Path,
    changelog_path: Path,
    today: str | None = None,
) -> tuple[str, str]:
    """Write the bumped pyproject and changelog. Returns (current, next) versions."""
    current, nxt, new_pyproject, new_changelog = plan_bump(
        part=part,
        pyproject_path=pyproject_path,
        changelog_path=changelog_path,
        today=today,
    )
    original_pyproject = pyproject_path.read_text(encoding="utf-8")
    original_changelog = changelog_path.read_text(encoding="utf-8")
    try:
        atomic_write_text(pyproject_path, new_pyproject)
        atomic_write_text(changelog_path, new_changelog)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path, original in (
            (pyproject_path, original_pyproject),
            (changelog_path, original_changelog),
        ):
            try:
                atomic_write_text(path, original)
            except OSError as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        if rollback_errors:
            raise ReleaseError(
                "Release update failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    return current, nxt


__all__ = [
    "BumpPart",
    "ReleaseError",
    "REPO_ROOT",
    "apply_bump",
    "bump_version",
    "check_consistency",
    "latest_git_tag",
    "parse_version",
    "plan_bump",
    "read_pyproject_version",
    "roll_changelog",
    "set_pyproject_version",
    "today_iso",
]
