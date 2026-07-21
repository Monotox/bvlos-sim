"""SITL evidence command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_sitl_support import (
    SitlLiveOptions,
    SitlScenarioContext,
    _build_sitl_evidence_from_context,
    _emit_sitl_progress,
    _load_sitl_scenario_context,
    _render_sitl_evidence_output,
    _resolve_sitl_live_options,
    _sitl_adapter_for_options,
)
from adapters.cli_support import OutputWriteError, _write_output
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.io import InputLoadError
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.sitl.ardupilot_types import ArduPilotAdapterError
from adapters.sitl.artifacts import SITL_ARTIFACT_FILENAMES
from adapters.assets.terrain_grid import TerrainGridLoadError
from adapters.assets.wind_grid import WindGridLoadError


def sitl(
    scenario_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    format: cli.DocumentOutputFormat = typer.Option(
        cli.DocumentOutputFormat.JSON,
        "--format",
        help="Output format for the SITL evidence bundle.",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Connect to a running ArduPilot SITL and record telemetry.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="ArduPilot SITL host. Used only with --live.",
    ),
    port: int = typer.Option(
        5760,
        "--port",
        help="ArduPilot SITL TCP port. Used only with --live.",
    ),
    artifact_dir: Path | None = typer.Option(
        None,
        "--artifact-dir",
        help=(
            "Directory for SITL artifact files (telemetry.json, command_log.json, etc.). "
            "Required with --live. Created if it does not exist."
        ),
    ),
    telemetry_samples: int = typer.Option(
        20,
        "--telemetry-samples",
        min=1,
        help="Number of MAVLink messages to record. Used only with --live.",
    ),
    telemetry_timeout_s: float = typer.Option(
        30.0,
        "--telemetry-timeout-s",
        min=1.0,
        help="Per-message receive timeout in seconds. Used only with --live.",
    ),
    mission_timeout_s: float = typer.Option(
        300.0,
        "--mission-timeout-s",
        min=1.0,
        help="Maximum time to wait for the uploaded mission to complete.",
    ),
) -> None:
    """Build contract-only or live ArduPilot SITL evidence from a scenario."""

    live_options = _resolve_sitl_live_options(
        live=live,
        host=host,
        port=port,
        artifact_dir=artifact_dir,
        telemetry_samples=telemetry_samples,
        telemetry_timeout_s=telemetry_timeout_s,
        mission_timeout_s=mission_timeout_s,
    )
    if live and live_options is None:
        cli._exit_with_cli_error(
            "--artifact-dir is required when --live is specified.",
            command="sitl",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    try:
        context = _load_sitl_scenario_context(scenario_file)
        _validate_sitl_paths(
            scenario_file=scenario_file,
            output=output,
            live_options=live_options,
            context=context,
        )
        adapter = _sitl_adapter_for_options(context, live_options)
        if live_options is not None:
            _emit_sitl_progress("Writing evidence bundle...")
        evidence = _build_sitl_evidence_from_context(
            context,
            adapter=adapter,
            live_options=live_options,
            reference_base_dir=(
                output.parent.resolve(strict=False)
                if output is not None
                else Path.cwd()
            ),
        )
        _write_output(
            _render_sitl_evidence_output(cli._document_output_format(format), evidence),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sitl",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except (
        GeofenceLoadError,
        LandingZoneLoadError,
        TerrainGridLoadError,
        WindGridLoadError,
        ValueError,
    ) as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sitl",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except ArduPilotAdapterError as exc:
        cli._exit_with_cli_error(
            f"SITL adapter error: {exc}",
            command="sitl",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sitl",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sitl",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )


def _validate_sitl_paths(
    *,
    scenario_file: Path,
    output: Path | None,
    live_options: SitlLiveOptions | None,
    context: SitlScenarioContext,
) -> None:
    input_paths = {
        scenario_file.resolve(strict=False),
        context.mission_document.path.resolve(strict=False),
        context.vehicle_document.path.resolve(strict=False),
        *(
            document.path.resolve(strict=False)
            for document in context.mission_assets.known_documents().values()
            if document is not None
        ),
    }
    if output is not None and output.resolve(strict=False) in input_paths:
        raise ValueError(f"--output {output} would overwrite a SITL input file")
    if live_options is None:
        return
    reserved = {
        (live_options.artifact_dir / filename).resolve(strict=False)
        for filename in SITL_ARTIFACT_FILENAMES
    }
    if output is not None and output.resolve(strict=False) in reserved:
        raise ValueError(
            f"--output {output} collides with a reserved SITL artifact filename"
        )
    collision = reserved.intersection(input_paths)
    if collision:
        path = min(collision, key=str)
        raise ValueError(f"SITL artifact path {path} would overwrite an input file")
