"""QGroundControl plan conversion command."""

import json
from pathlib import Path

import typer
import yaml

import adapters.cli as cli
from adapters.cli_support import OutputWriteError, _write_output
from adapters.qgc_plan import load_and_convert_plan


def convert(
    plan: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Convert a QGroundControl .plan file to a mission.v5 YAML."""

    try:
        mission, diagnostics = load_and_convert_plan(plan)
        for diagnostic in diagnostics:
            typer.echo(
                "Warning: item "
                f"{diagnostic.item_index} (command {diagnostic.command}): "
                f"{diagnostic.message}",
                err=True,
            )
        rendered = yaml.dump(
            mission,
            default_flow_style=False,
            sort_keys=False,
        )
        _write_output(rendered, output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except (json.JSONDecodeError, ValueError) as exc:
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
