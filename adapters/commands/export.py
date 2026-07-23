"""QGroundControl plan export command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import (
    NO_CLOBBER_OPTION,
    OutputWriteError,
    _refuse_output_clobber,
    _write_output,
)
from adapters.io import InputLoadError, load_mission
from adapters.preflight import check_file, emit_preflight, is_json_format
from adapters.qgc_export import (
    ExportDiagnostic,
    build_qgc_plan,
    lossy_export_summary,
    render_qgc_plan,
)


def _emit_export_diagnostics(diagnostics: list[ExportDiagnostic]) -> None:
    """Print per-diagnostic warnings and the one-line lossy summary to stderr.

    Export keeps exit 0 for these: the .plan format cannot represent the
    rewritten or omitted content (a documented QGC limitation, not an error).
    """
    for diagnostic in diagnostics:
        scope = (
            f"item {diagnostic.route_item_id}"
            if diagnostic.route_item_id is not None
            else "mission"
        )
        typer.echo(f"Warning: {scope}: {diagnostic.message}", err=True)
    summary = lossy_export_summary(diagnostics)
    if summary is not None:
        typer.echo(summary, err=True)


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
        _emit_export_diagnostics(diagnostics)
        text_lines.append(
            f"mission: {mission.name}: OK ({len(mission_model.route)} route items)"
        )

    emit_preflight(
        command="export", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def export(
    mission: Path = typer.Argument(
        ...,
        resolve_path=True,
        help="Path to mission.v7 YAML file.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the .plan JSON to a file instead of stdout."
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
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

    _refuse_output_clobber(output, no_clobber=no_clobber, command="export")

    try:
        mission_model, _document = load_mission(mission)
        plan, diagnostics = build_qgc_plan(mission_model)
        _emit_export_diagnostics(diagnostics)
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
