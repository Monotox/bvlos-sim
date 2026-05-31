"""SORA pre-assessment command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _write_output,
)
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.sora_envelope import build_sora_envelope, render_sora_envelope_json
from adapters.sora_markdown import render_sora_markdown
from estimator.execution.sora import build_sora_assessment


def sora(
    mission: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to mission.v6 YAML file.",
    ),
    vehicle: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to vehicle profile YAML file.",
    ),
    format: cli.SoraOutputFormat = typer.Option(
        cli.SoraOutputFormat.MARKDOWN,
        "--format",
        help="Output format: markdown for the SORA report, json for the envelope.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate mission and vehicle files against their schemas and exit "
            "without running the pre-assessment."
        ),
    ),
) -> None:
    """Run the SORA pre-assessment (Ground Risk, Air Risk, and SAIL)."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    try:
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        if validate_only:
            typer.echo(f"mission: {mission.name}: OK")
            typer.echo(f"vehicle: {vehicle.name}: OK")
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        result = cli.try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            population_provider=mission_assets.population_provider,
            obstacle_provider=mission_assets.obstacle_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        assessment = build_sora_assessment(mission_model, vehicle_model, result)
        envelope = build_sora_envelope(
            result=assessment,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            population_document=mission_assets.population_document,
        )
        if format == cli.SoraOutputFormat.JSON:
            rendered = render_sora_envelope_json(envelope)
        else:
            rendered = render_sora_markdown(envelope)
        _write_output(rendered, output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INVALID_INPUT,
            details={"input_name": exc.input_name, "stage": str(exc.stage)},
        )
    except (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError) as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError:
        cli._exit_with_cli_error(
            "Failed to write SORA output.",
            command="sora",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
