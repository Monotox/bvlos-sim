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
    vehicle_profile: str | None = typer.Option(
        None,
        "--vehicle-profile",
        help=(
            "Vehicle profile id to write into the converted mission YAML. "
            "Must match the vehicle_id in the vehicle profile YAML you intend to use. "
            "Required."
        ),
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write converted YAML to file instead of stdout."),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Parse and validate the .plan file without writing output. "
            "Exits 0 when the file is valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Convert a QGroundControl .plan file to a mission.v6 YAML."""

    if not vehicle_profile or not vehicle_profile.strip():
        typer.echo(
            "Error: --vehicle-profile is required. "
            "Pass the vehicle_id from the vehicle profile you intend to use, "
            "e.g. --vehicle-profile quadplane_v1",
            err=True,
        )
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT))

    try:
        mission, diagnostics = load_and_convert_plan(plan, vehicle_profile=vehicle_profile.strip())
        for diagnostic in diagnostics:
            typer.echo(
                "Warning: item "
                f"{diagnostic.item_index} (command {diagnostic.command}): "
                f"{diagnostic.message}",
                err=True,
            )
        if validate_only:
            typer.echo(f"plan: {plan.name}: OK ({len(mission.get('route', []))} route items)")
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
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
