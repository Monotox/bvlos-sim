"""Version bump and release-consistency command."""

from pathlib import Path

import typer

import adapters.cli_contract as cli
from adapters.release import (
    BumpPart,
    ReleaseError,
    apply_bump,
    check_consistency,
    latest_git_tag,
    plan_bump,
    read_pyproject_version,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"
_CHANGELOG_PATH = _REPO_ROOT / "CHANGELOG.md"


def bump(
    part: BumpPart | None = typer.Argument(
        None,
        help="Which semver component to bump: major, minor, or patch.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the next version and the exact edits without modifying any file.",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help="Verify pyproject.toml is not behind the latest git tag; exit non-zero on drift.",
    ),
) -> None:
    """Bump the project version, rolling CHANGELOG.md, or check release consistency.

    Never creates tags, pushes, or publishes — it only edits files and prints the
    suggested follow-up commands.
    """
    try:
        if check:
            _run_check()
            return
        if part is None:
            cli._exit_with_cli_error(
                "Specify a version part (major, minor, or patch) or use --check.",
                command="bump",
                code=cli.CliExitCode.INVALID_INPUT,
            )
        _run_bump(part, dry_run=dry_run)
    except ReleaseError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="bump",
            code=cli.CliExitCode.INVALID_INPUT,
        )


def _run_check() -> None:
    pyproject_version = read_pyproject_version(
        _PYPROJECT_PATH.read_text(encoding="utf-8")
    )
    tag = latest_git_tag()
    problems = check_consistency(pyproject_version, tag)
    typer.echo(f"pyproject.toml: {pyproject_version}")
    typer.echo(f"latest git tag: {tag or '(none)'}")
    if problems:
        for problem in problems:
            typer.echo(f"INCONSISTENT: {problem}")
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT))
    typer.echo("OK: version sources are consistent.")
    raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))


def _run_bump(part: BumpPart, *, dry_run: bool) -> None:
    if dry_run:
        current, nxt, _, _ = plan_bump(
            part=part,
            pyproject_path=_PYPROJECT_PATH,
            changelog_path=_CHANGELOG_PATH,
        )
        typer.echo(f"Would bump {current} -> {nxt} ({part.value})")
        typer.echo("  pyproject.toml: update version")
        typer.echo(f"  CHANGELOG.md:   roll [Unreleased] into [{nxt}]")
        typer.echo("No files modified (--dry-run).")
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))

    current, nxt = apply_bump(
        part=part,
        pyproject_path=_PYPROJECT_PATH,
        changelog_path=_CHANGELOG_PATH,
    )
    typer.echo(f"Bumped {current} -> {nxt} ({part.value})")
    typer.echo("Updated pyproject.toml and CHANGELOG.md.")
    typer.echo("")
    typer.echo("Next steps (run manually to release):")
    typer.echo(f"  git commit -am 'chore: release v{nxt}'")
    typer.echo(f"  git tag v{nxt}")
    typer.echo(f"  git push && git push origin v{nxt}")
    raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
