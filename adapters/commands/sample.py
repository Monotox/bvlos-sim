"""Monte Carlo uncertainty sample command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _render_uncertainty_output,
    _write_output,
)
from adapters.io import InputLoadError, load_mission, load_vehicle
from adapters.uncertainty_envelope import build_uncertainty_envelope
from adapters.uncertainty_io import load_uncertainty_plan, resolve_uncertainty_asset_path


def sample(
    uncertainty_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True,
        help="Path to uncertainty.v1 YAML file.",
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
            "Validate uncertainty, mission, and vehicle files against their schemas "
            "and exit without running the sampler. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Run a seeded Monte Carlo uncertainty analysis and emit an uncertainty report."""

    uncertainty_document = None
    mission_document = None
    vehicle_document = None
    mission_assets = MissionAssetBundle()

    try:
        plan, uncertainty_document = load_uncertainty_plan(uncertainty_file)

        mission_path = resolve_uncertainty_asset_path(
            plan.mission_file, uncertainty_path=uncertainty_file
        )
        vehicle_path = resolve_uncertainty_asset_path(
            plan.vehicle_file, uncertainty_path=uncertainty_file
        )

        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)
        if validate_only:
            typer.echo(f"uncertainty: {uncertainty_file.name}: OK")
            typer.echo(f"mission: {mission_path.name}: OK")
            typer.echo(f"vehicle: {vehicle_path.name}: OK")
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = cli.run_monte_carlo(
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
        envelope = build_uncertainty_envelope(
            result=result,
            uncertainty_document=uncertainty_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        _write_output(
            _render_uncertainty_output(cli._summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
