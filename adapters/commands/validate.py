"""Predicted-vs-observed validation command."""

from pathlib import Path

import typer
from pydantic import ValidationError

import adapters.cli as cli
from adapters.calibration import load_and_apply_calibration
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.canonical_json import render_canonical_json
from adapters.cli_support import (
    NO_CLOBBER_OPTION,
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _refuse_output_clobber,
    _write_output,
)
from adapters.flight_log import load_flight_trace
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.phase_segmentation import segment_trace
from adapters.validation import build_validation_report
from adapters.validation_markdown import render_validation_markdown
from adapters.version import tool_version
from schemas.flight_log import FlightTraceMissionRef


def validate(
    mission: Path = typer.Argument(
        ...,
        resolve_path=True,
        help="Path to mission.v7 YAML file.",
    ),
    vehicle: Path = typer.Argument(
        ...,
        resolve_path=True,
        help="Path to vehicle profile YAML file.",
    ),
    trace: Path = typer.Argument(
        ...,
        resolve_path=True,
        help="Path to a flight-trace.v1 JSON file (from flight-log ingestion).",
    ),
    validation_id: str | None = typer.Option(
        None,
        "--validation-id",
        help="Stable validation report identifier. Defaults to <trace_id>-validation.",
    ),
    calibration: Path | None = typer.Option(
        None,
        "--calibration",
        resolve_path=True,
        help=(
            "Optional calibration-profile.v1 JSON to layer on the vehicle before "
            "estimating. Overrides matching performance fields; must reference this "
            "vehicle_id."
        ),
    ),
    format: cli.DocumentOutputFormat = typer.Option(
        cli.DocumentOutputFormat.MARKDOWN,
        "--format",
        help="Output format: markdown for the report, json for the validation-report.v2 envelope.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
    max_time_error_percent: float = typer.Option(
        20.0, "--max-time-error-percent", min=0.0
    ),
    max_distance_error_percent: float = typer.Option(
        10.0, "--max-distance-error-percent", min=0.0
    ),
    max_speed_error_percent: float = typer.Option(
        15.0, "--max-speed-error-percent", min=0.0
    ),
    max_reserve_error_percent: float = typer.Option(
        10.0, "--max-reserve-error-percent", min=0.0
    ),
) -> None:
    """Compare a deterministic mission estimate against an observed flight trace."""

    _refuse_output_clobber(output, no_clobber=no_clobber, command="validate")

    mission_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    try:
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        if calibration is not None:
            vehicle_model = load_and_apply_calibration(vehicle_model, calibration)
        normalized_trace, _trace_document = load_flight_trace(trace)
        _validate_trace_references(
            normalized_trace.mission_ref,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        estimate = cli.try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            population_provider=mission_assets.population_provider,
            obstacle_provider=mission_assets.obstacle_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        segments = segment_trace(normalized_trace)
        report = build_validation_report(
            estimate=estimate,
            trace=normalized_trace,
            segments=segments,
            validation_id=validation_id or f"{normalized_trace.trace_id}-validation",
            tool_version=tool_version(),
            acceptance_thresholds_pct={
                "time_s": max_time_error_percent,
                "horizontal_distance_m": max_distance_error_percent,
                "mean_groundspeed_mps": max_speed_error_percent,
                "reserve_percent": max_reserve_error_percent,
            },
        )

        if format == cli.DocumentOutputFormat.JSON:
            rendered = render_canonical_json(report.model_dump(mode="json"))
        else:
            rendered = render_validation_markdown(report)
        _write_output(rendered, output)
        exit_code = (
            cli.CliExitCode.SUCCESS
            if report.acceptance.passed
            else cli.CliExitCode.INFEASIBLE
        )
        raise typer.Exit(code=int(exit_code))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="validate",
            code=cli.CliExitCode.INVALID_INPUT,
            details={"input_name": exc.input_name, "stage": str(exc.stage)},
        )
    except (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError) as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="validate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        cli._exit_with_cli_error(
            f"validation_id: {first['msg']}",
            command="validate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="validate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError:
        cli._exit_with_cli_error(
            "Failed to write validation output.",
            command="validate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="validate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )


def _validate_trace_references(
    mission_ref: FlightTraceMissionRef | None,
    *,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
) -> None:
    if mission_ref is None:
        raise ValueError(
            "Flight trace has no mission_ref; validation requires content-linked mission and vehicle inputs"
        )
    if mission_ref.mission_sha256 is None or mission_ref.vehicle_sha256 is None:
        raise ValueError(
            "Flight trace mission_ref must include mission_sha256 and vehicle_sha256"
        )
    if mission_ref.mission_sha256.lower() != mission_document.sha256.lower():
        raise ValueError(
            "Flight trace mission_sha256 does not match the supplied mission"
        )
    if mission_ref.vehicle_sha256.lower() != vehicle_document.sha256.lower():
        raise ValueError(
            "Flight trace vehicle_sha256 does not match the supplied vehicle"
        )
