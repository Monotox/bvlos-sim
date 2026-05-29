"""QGroundControl plan export command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import OutputWriteError, _write_output
from adapters.io import InputLoadError, load_mission
from adapters.qgc_export import build_qgc_plan, render_qgc_plan


def export(
    mission: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True, help="Path to mission.v6 YAML file."
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
) -> None:
    """Export a mission.v6 YAML to a QGroundControl .plan file."""

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
        if validate_only:
            typer.echo(
                f"mission: {mission.name}: OK ({len(mission_model.route)} route items)"
            )
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
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
