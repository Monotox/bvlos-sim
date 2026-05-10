"""Typer CLI adapter for estimator execution."""

from enum import IntEnum
from pathlib import Path

import typer
from pydantic import ValidationError

from adapters.envelope import (
    EnvelopeInputs,
    EstimatorResultEnvelope,
    OutputFormat,
    build_estimator_envelope,
    build_internal_error_envelope,
    build_invalid_input_envelope,
    render_envelope_json,
)
from adapters.geofence_geojson import GeofenceLoadError, load_geofences
from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    load_mission,
    load_vehicle,
    validation_error_summary,
)
from adapters.landing_zone_geojson import LandingZoneLoadError, load_landing_zones
from adapters.markdown import render_envelope_markdown
from adapters.scenario_envelope import (
    ScenarioResultEnvelope,
    build_scenario_envelope,
    build_scenario_internal_error_envelope,
    build_scenario_invalid_input_envelope,
    render_scenario_envelope_json,
)
from adapters.scenario_io import load_scenario, resolve_scenario_asset_path
from adapters.scenario_markdown import render_scenario_markdown
from adapters.terrain_grid import TerrainGridLoadError, load_terrain_grid
from estimator import (
    EstimateStatus,
    EstimationOptions,
    EstimatorFailure,
    FailureKind,
    FidelityMode,
    LayeredWindProvider,
    MissionEstimate,
    ScenarioStatus,
    WindLayer,
    run_scenario,
    try_estimate_mission_distance_time,
)

StaticAssetLoadError = GeofenceLoadError | LandingZoneLoadError | TerrainGridLoadError

app = typer.Typer(name="bvlos-sim", add_completion=False, no_args_is_help=True)


class CliExitCode(IntEnum):
    SUCCESS = 0
    INFEASIBLE = 10
    INVALID_INPUT = 11
    UNSUPPORTED = 12
    INTERNAL_ERROR = 13


class ScenarioExitCode(IntEnum):
    PASSED = 0
    FAILED = 10
    INVALID_INPUT = 11
    INTERNAL_ERROR = 13


class OutputWriteError(OSError):
    """Raised when the CLI cannot write rendered output."""


@app.callback()
def main() -> None:
    """BVLOS simulator command group."""


def _render_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
) -> str:
    if output_format == OutputFormat.MARKDOWN:
        return render_envelope_markdown(envelope)
    return render_envelope_json(envelope)


def _render_scenario_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
) -> str:
    if output_format == OutputFormat.MARKDOWN:
        return render_scenario_markdown(envelope)
    return render_scenario_envelope_json(envelope)


def _write_output(rendered: str, output: Path | None) -> None:
    try:
        if output is None:
            typer.echo(rendered, nl=False)
            return
        output.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError("Failed to write estimator output.") from exc


def _exit_code_for_result(result: MissionEstimate) -> CliExitCode:
    if result.status == EstimateStatus.SUCCESS:
        return CliExitCode.SUCCESS
    if result.failure is None:
        return CliExitCode.INTERNAL_ERROR
    if result.failure.kind == FailureKind.INFEASIBLE:
        return CliExitCode.INFEASIBLE
    if result.failure.kind == FailureKind.UNSUPPORTED:
        return CliExitCode.UNSUPPORTED
    return CliExitCode.INVALID_INPUT


def _status_for_failure_kind(kind: FailureKind) -> EstimateStatus:
    if kind == FailureKind.INFEASIBLE:
        return EstimateStatus.INFEASIBLE
    return EstimateStatus.ERROR


def _empty_failed_result(failure: EstimatorFailure) -> MissionEstimate:
    return MissionEstimate(
        status=_status_for_failure_kind(failure.kind),
        total_horizontal_distance_m=0.0,
        total_vertical_distance_m=0.0,
        total_path_distance_m=0.0,
        total_time_s=0.0,
        totals_are_partial=False,
        legs=[],
        energy=None,
        geofence=None,
        landing_zone=None,
        warnings=[],
        failure=failure,
        metadata={},
    )


_WIND_LAYER_FLAG = "--wind-layer"
_MAX_SEGMENT_FLAG = "--max-segment-length-m"
_FIDELITY_FLAG = "--fidelity"


def _parse_wind_layer_entry(i: int, entry: str) -> WindLayer:
    parts = entry.split(":")
    if len(parts) != 3:
        raise InputLoadError(
            f"{_WIND_LAYER_FLAG} entry {i} must be formatted as ALT_M:EAST_MPS:NORTH_MPS.",
            input_name=_WIND_LAYER_FLAG,
            path=Path(_WIND_LAYER_FLAG),
            stage=InputLoadStage.PARSE,
            details={"entry_index": i, "raw": entry},
        )
    try:
        altitude_m, east, north = float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        raise InputLoadError(
            f"{_WIND_LAYER_FLAG} entry {i}: all three values must be numeric.",
            input_name=_WIND_LAYER_FLAG,
            path=Path(_WIND_LAYER_FLAG),
            stage=InputLoadStage.PARSE,
            details={"entry_index": i, "raw": entry},
        )
    return WindLayer(altitude_m=altitude_m, wind_east_mps=east, wind_north_mps=north)


def _parse_wind_layers(raw: list[str]) -> list[WindLayer]:
    return [_parse_wind_layer_entry(i, entry) for i, entry in enumerate(raw)]


def _build_estimation_options(
    fidelity: FidelityMode | None,
    max_segment_length_m: float | None,
) -> EstimationOptions | None:
    if fidelity is None and max_segment_length_m is None:
        return None
    try:
        return EstimationOptions(
            fidelity=FidelityMode.V1 if fidelity is None else fidelity,
            max_segment_length_m=max_segment_length_m,
        )
    except ValidationError as exc:
        raise InputLoadError(
            f"{_MAX_SEGMENT_FLAG} must be a positive number.",
            input_name=_MAX_SEGMENT_FLAG,
            path=Path(_MAX_SEGMENT_FLAG),
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
        ) from exc


def _resolve_asset_path(path: Path, *, mission_path: Path) -> Path:
    if path.is_absolute():
        return path
    return mission_path.parent / path


def _envelope_inputs_for_static_asset_error(
    error: StaticAssetLoadError,
    *,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
    geofence_document: InputDocument | None,
    landing_zone_document: InputDocument | None,
    terrain_document: InputDocument | None,
) -> EnvelopeInputs | None:
    if mission_document is None or vehicle_document is None:
        return None

    return EnvelopeInputs(
        mission=mission_document,
        vehicle=vehicle_document,
        geofences=(
            error.document
            if isinstance(error, GeofenceLoadError)
            else geofence_document
        ),
        landing_zones=(
            error.document
            if isinstance(error, LandingZoneLoadError)
            else landing_zone_document
        ),
        terrain=(
            error.document
            if isinstance(error, TerrainGridLoadError)
            else terrain_document
        ),
    )


def _write_internal_error_envelope(
    *,
    error: Exception,
    output_format: OutputFormat,
    output: Path | None,
    inputs: EnvelopeInputs | None,
    retry_requested_output: bool,
) -> None:
    envelope = build_internal_error_envelope(error=error, inputs=inputs)
    rendered = _render_output(output_format, envelope)
    destinations: list[Path | None] = [output] if retry_requested_output else []
    if output is not None:
        destinations.append(None)

    for destination in destinations:
        try:
            _write_output(rendered, destination)
            return
        except OutputWriteError:
            continue

    typer.echo("Failed to write estimator output.", err=True)


@app.command()
def estimate(
    mission: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    vehicle: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    wind_layer: list[str] | None = typer.Option(
        None,
        "--wind-layer",
        help=(
            "Wind layer as ALT_M:EAST_MPS:NORTH_MPS. "
            "Repeat to specify multiple layers. "
            "Overrides mission estimation wind."
        ),
    ),
    max_segment_length_m: float | None = typer.Option(
        None,
        "--max-segment-length-m",
        help="Sub-segment wind sampling interval in metres (must be > 0).",
    ),
    fidelity: FidelityMode | None = typer.Option(
        None,
        "--fidelity",
        help=(
            "Estimator fidelity mode: v1 or v2. "
            "Overrides mission estimation fidelity when provided."
        ),
    ),
) -> None:
    """Run the deterministic estimator and emit a stable result envelope."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    geofence_document: InputDocument | None = None
    landing_zone_document: InputDocument | None = None
    terrain_document: InputDocument | None = None
    envelope_inputs: EnvelopeInputs | None = None
    try:
        options = _build_estimation_options(fidelity, max_segment_length_m)
        wind_provider = LayeredWindProvider(_parse_wind_layers(wind_layer)) if wind_layer else None
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        terrain_provider = None
        if mission_model.assets.terrain_file is not None:
            terrain_path = _resolve_asset_path(
                mission_model.assets.terrain_file,
                mission_path=mission_document.path,
            )
            terrain_provider, terrain_document = load_terrain_grid(terrain_path)
        geofences = None
        if mission_model.assets.geofences_file is not None:
            geofence_path = _resolve_asset_path(
                mission_model.assets.geofences_file,
                mission_path=mission_document.path,
            )
            geofences, geofence_document = load_geofences(geofence_path)
        landing_zones = None
        if mission_model.assets.landing_zones_file is not None:
            landing_zone_path = _resolve_asset_path(
                mission_model.assets.landing_zones_file,
                mission_path=mission_document.path,
            )
            landing_zones, landing_zone_document = load_landing_zones(landing_zone_path)
        envelope_inputs = EnvelopeInputs(
            mission=mission_document,
            vehicle=vehicle_document,
            geofences=geofence_document,
            landing_zones=landing_zone_document,
            terrain=terrain_document,
        )
        result = try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            options=options,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
        envelope = build_estimator_envelope(
            result=result,
            inputs=envelope_inputs,
        )
        _write_output(_render_output(format, envelope), output)
        raise typer.Exit(code=int(_exit_code_for_result(result)))
    except InputLoadError as exc:
        envelope = build_invalid_input_envelope(
            error=exc,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        try:
            _write_output(_render_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _write_internal_error_envelope(
                error=write_exc,
                output_format=format,
                output=output,
                inputs=envelope_inputs,
                retry_requested_output=False,
            )
            raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except (GeofenceLoadError, LandingZoneLoadError) as exc:
        result = _empty_failed_result(exc.failure)
        asset_error_inputs = _envelope_inputs_for_static_asset_error(
            exc,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            geofence_document=geofence_document,
            landing_zone_document=landing_zone_document,
            terrain_document=terrain_document,
        )
        if asset_error_inputs is not None:
            envelope_inputs = asset_error_inputs
            envelope = build_estimator_envelope(
                result=result,
                inputs=envelope_inputs,
            )
        else:
            envelope = build_internal_error_envelope(error=exc, inputs=envelope_inputs)
        try:
            _write_output(_render_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _write_internal_error_envelope(
                error=write_exc,
                output_format=format,
                output=output,
                inputs=envelope_inputs,
                retry_requested_output=False,
            )
            raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(_exit_code_for_result(result))) from exc
    except OutputWriteError as exc:
        _write_internal_error_envelope(
            error=exc,
            output_format=format,
            output=output,
            inputs=envelope_inputs,
            retry_requested_output=False,
        )
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        _write_internal_error_envelope(
            error=exc,
            output_format=format,
            output=output,
            inputs=envelope_inputs,
            retry_requested_output=True,
        )
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc


def _emit_scenario_internal_error(
    *,
    output_format: OutputFormat,
    scenario_id: str,
    scenario_document: InputDocument | None,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
) -> None:
    internal_envelope = build_scenario_internal_error_envelope(
        scenario_id=scenario_id,
        known_documents={
            "scenario": scenario_document,
            "mission": mission_document,
            "vehicle": vehicle_document,
        },
    )
    _write_output(_render_scenario_output(output_format, internal_envelope), None)


@app.command()
def scenario(
    scenario_file: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Run the deterministic scenario runner and emit a scenario result envelope."""

    scenario_document: InputDocument | None = None
    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    scenario_id = "<unknown>"

    try:
        scenario_plan, scenario_document = load_scenario(scenario_file)
        scenario_id = scenario_plan.scenario_id

        mission_path = resolve_scenario_asset_path(
            scenario_plan.mission_file, scenario_path=scenario_file
        )
        vehicle_path = resolve_scenario_asset_path(
            scenario_plan.vehicle_file, scenario_path=scenario_file
        )

        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)

        result = run_scenario(scenario_plan, mission_model, vehicle_model)
        envelope = build_scenario_envelope(
            result=result,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        _write_output(_render_scenario_output(format, envelope), output)
        exit_code = (
            ScenarioExitCode.PASSED
            if result.status == ScenarioStatus.PASSED
            else ScenarioExitCode.FAILED
        )
        raise typer.Exit(code=int(exit_code))
    except InputLoadError as exc:
        envelope = build_scenario_invalid_input_envelope(
            scenario_id=scenario_id,
            error=exc,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        try:
            _write_output(_render_scenario_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _emit_scenario_internal_error(
                output_format=format,
                scenario_id=scenario_id,
                scenario_document=scenario_document,
                mission_document=mission_document,
                vehicle_document=vehicle_document,
            )
            raise typer.Exit(code=int(ScenarioExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(ScenarioExitCode.INVALID_INPUT)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        _emit_scenario_internal_error(
            output_format=format,
            scenario_id=scenario_id,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        raise typer.Exit(code=int(ScenarioExitCode.INTERNAL_ERROR)) from exc
