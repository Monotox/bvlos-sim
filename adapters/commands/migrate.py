"""Schema migration command."""

import difflib
from dataclasses import dataclass
import json
from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

import adapters.cli_contract as cli
from adapters.atomic_write import atomic_write_text
from adapters.cli_support import NO_CLOBBER_OPTION, _refuse_output_clobber
from adapters.migration import detect_mission_version, migrate_payload
from schemas.mission import MISSION_SCHEMA_VERSION, MissionPlan


@dataclass(frozen=True, slots=True)
class _MigrationPlan:
    message: str
    destination: Path | None = None
    rendered: str | None = None
    backup_path: Path | None = None
    backup_content: str | None = None


def _parse_mapping(path: Path) -> tuple[dict[str, object], str, str]:
    suffix = path.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        raise ValueError(
            f"Unsupported migration input format {suffix or '<none>'}; use JSON or YAML"
        )
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read migration input: {path}") from exc
    try:
        parsed = json.loads(original) if suffix == ".json" else yaml.safe_load(original)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to parse migration input: {path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Migration input must contain a mapping/object at the root")
    return parsed, original, "json" if suffix == ".json" else "yaml"


def _render(payload: dict[str, object], format_name: str) -> str:
    if format_name == "json":
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _plan_migration(
    path: Path,
    *,
    dry_run: bool,
    backup: bool,
    output: Path | None,
) -> _MigrationPlan:
    payload, original, format_name = _parse_mapping(path)
    detected = detect_mission_version(payload)
    if detected == MISSION_SCHEMA_VERSION:
        try:
            MissionPlan.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                f"{path}: declared {MISSION_SCHEMA_VERSION} but failed validation: {exc}"
            ) from exc
        header = f"{path}: already at latest version {MISSION_SCHEMA_VERSION}"
        if output is not None and output.resolve(strict=False) != path.resolve(
            strict=False
        ):
            if dry_run:
                return _MigrationPlan(message=f"{header}; would write {output}")
            return _MigrationPlan(
                message=f"{header}; wrote {output}",
                destination=output,
                rendered=original,
            )
        return _MigrationPlan(message=header)

    migrated = migrate_payload(
        "mission",
        payload,
        from_version=detected,
        target_version=MISSION_SCHEMA_VERSION,
    )
    try:
        MissionPlan.model_validate(migrated)
    except ValidationError as exc:
        raise ValueError(
            f"Migrated mission failed {MISSION_SCHEMA_VERSION} validation: {exc}"
        ) from exc
    rendered = _render(migrated, format_name)
    header = f"{path}: {detected} -> {MISSION_SCHEMA_VERSION}"
    if dry_run:
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=str(path),
                tofile=f"{path} ({MISSION_SCHEMA_VERSION})",
            )
        )
        return _MigrationPlan(message=f"{header}\n{diff}".rstrip())

    destination = output or path
    backup_path: Path | None = None
    if backup and output is None:
        backup_path = Path(f"{path}.bak")
        if backup_path.exists():
            raise ValueError(f"Backup already exists: {backup_path}")
    return _MigrationPlan(
        message=f"{header}; wrote {destination}",
        destination=destination,
        rendered=rendered,
        backup_path=backup_path,
        backup_content=original if backup_path is not None else None,
    )


def _apply_migration(plan: _MigrationPlan) -> None:
    if plan.backup_path is not None:
        assert plan.backup_content is not None
        atomic_write_text(plan.backup_path, plan.backup_content)
    if plan.destination is not None:
        assert plan.rendered is not None
        atomic_write_text(plan.destination, plan.rendered)


def migrate(
    path: Path = typer.Argument(..., help="Mission YAML/JSON file or directory."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print detected/target versions and a diff without writing.",
    ),
    backup: bool = typer.Option(
        False,
        "--backup",
        help="Before an in-place write, save the original as FILE.bak.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write one migrated file to a separate path.",
    ),
    glob_pattern: str = typer.Option(
        "*.yaml",
        "--glob",
        help="Pattern used when PATH is a directory (default: *.yaml).",
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
) -> None:
    """Migrate mission.v6 YAML/JSON inputs to mission.v7."""

    _refuse_output_clobber(output, no_clobber=no_clobber, command="migrate")

    try:
        if not path.exists():
            raise ValueError(f"Migration path does not exist: {path}")
        if path.is_dir():
            if output is not None:
                raise ValueError("--output is only valid when migrating one file")
            files = sorted(
                candidate
                for candidate in path.glob(glob_pattern)
                if candidate.is_file()
            )
            if not files:
                raise ValueError(f"No files matched {glob_pattern!r} in {path}")
        else:
            files = [path]
        plans = [
            _plan_migration(
                source,
                dry_run=dry_run,
                backup=backup,
                output=output,
            )
            for source in files
        ]
        for plan in plans:
            _apply_migration(plan)
            typer.echo(plan.message)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT)) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - every other command has this net
        typer.echo(f"Internal error: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc


__all__ = ["migrate"]
