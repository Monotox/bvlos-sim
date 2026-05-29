"""Stochastic propagation command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _render_stochastic_output,
    _write_output,
)
from adapters.io import InputLoadError, load_mission, load_vehicle
from adapters.stochastic_envelope import build_stochastic_envelope
from adapters.stochastic_io import load_stochastic_plan, resolve_stochastic_asset_path


def propagate(
    stochastic_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True,
        help="Path to stochastic.v1 YAML file.",
    ),
    format: cli.SummaryOutputFormat = typer.Option(
        cli.SummaryOutputFormat.JSON,
        "--format",
        help="Output format. Use summary for a one-line feasibility and reserve result.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write output to file instead of stdout."),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate stochastic, mission, and vehicle files against their schemas "
            "and exit without running propagation. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Run stochastic state propagation and emit a stochastic-envelope.v1 report."""

    stochastic_document = None
    mission_document = None
    vehicle_document = None
    mission_assets = MissionAssetBundle()

    try:
        plan, stochastic_document = load_stochastic_plan(stochastic_file)

        mission_path = resolve_stochastic_asset_path(
            plan.mission_file, stochastic_path=stochastic_file
        )
        vehicle_path = resolve_stochastic_asset_path(
            plan.vehicle_file, stochastic_path=stochastic_file
        )

        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)
        if validate_only:
            typer.echo(f"stochastic: {stochastic_file.name}: OK")
            typer.echo(f"mission: {mission_path.name}: OK")
            typer.echo(f"vehicle: {vehicle_path.name}: OK")
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = cli.run_stochastic_propagation(
            plan,
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            population_provider=mission_assets.population_provider,
            obstacle_provider=mission_assets.obstacle_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        envelope = build_stochastic_envelope(
            result=result,
            stochastic_document=stochastic_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        _write_output(
            _render_stochastic_output(cli._summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
