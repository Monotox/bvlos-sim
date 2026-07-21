"""QGroundControl plan export command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import OutputWriteError, _write_output
from adapters.io import InputLoadError, load_mission
from adapters.preflight import check_file, emit_preflight, is_json_format
from adapters.qgc_export import build_qgc_plan, render_qgc_plan


def _run_export_preflight(*, mission: Path, as_json: bool) -> None:
    """Validate the mission YAML and its exportability without writing output."""

    def load_and_build():
        mission_model, _document = load_mission(mission)
        _plan, diagnostics = build_qgc_plan(mission_model)
        return mission_model, diagnostics

    files = []
    text_lines = []
    check, loaded = check_file(
        role="mission", path_str=mission.name, loader=load_and_build
    )
    files.append(check)
    if check.ok and loaded is not None:
        mission_model, diagnostics = loaded
        for diagnostic in diagnostics:
            scope = (
                f"item {diagnostic.route_item_id}"
                if diagnostic.route_item_id is not None
                else "mission"
            )
            typer.echo(f"Warning: {scope}: {diagnostic.message}", err=True)
        text_lines.append(
            f"mission: {mission.name}: OK ({len(mission_model.route)} route items)"
        )

    emit_preflight(
        command="export", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def export(
    mission: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to mission.v7 YAML file.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the .plan JSON to a file instead of stdout."
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate the mission YAML and its exportability without writing "
            "output. Exits 0 when valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Export a mission.v7 YAML to a QGroundControl .plan file."""

    if validate_only:
        _run_export_preflight(mission=mission, as_json=is_json_format(validate_format))

    try:
        mission_model, _document = load_mission(mission)
        plan, diagnostics = build_qgc_plan(mission_model)
        for diagnostic in diagnostics:
            scope = (
                f"item {diagnostic.route_item_id}"
                if diagnostic.route_item_id is not None
                else "mission"
            )
            typer.echo(f"Warning: {scope}: {diagnostic.message}", err=True)
        _write_output(render_qgc_plan(plan), output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
