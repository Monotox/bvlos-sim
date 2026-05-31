"""Deterministic estimate command."""

from collections.abc import Callable
from pathlib import Path

import typer

import adapters.cli as cli
from adapters.calibration import load_and_apply_calibration
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _build_estimation_options,
    _empty_failed_result,
    _envelope_inputs_for_static_asset_error,
    _envelope_output_format,
    _parse_wind_layers,
    _populate_mission_assets,
    _render_output,
    _write_output,
)
from adapters.envelope import (
    EnvelopeInputs,
    EstimatorResultEnvelope,
    OutputFormat,
    build_estimator_envelope,
    build_internal_error_envelope,
    build_invalid_input_envelope,
)
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.geojson_export import build_geojson_export
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.kml_export import build_kml_export
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.profile_markdown import render_profile_markdown
from adapters.sensitivity import render_sensitivity_markdown, run_sensitivity_sweep
from estimator import (
    EstimateStatus,
    EstimationOptions,
    FailureKind,
    FidelityMode,
    LayeredWindProvider,
    MissionEstimate,
    WindProvider,
)
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile

_FAILURE_KIND_EXIT_CODES = {
    FailureKind.INFEASIBLE: cli.CliExitCode.INFEASIBLE,
    FailureKind.UNSUPPORTED: cli.CliExitCode.UNSUPPORTED,
}


def _split_sensitivity_steps(raw: str, option_name: str) -> list[str]:
    steps = [part.strip() for part in raw.split(",") if part.strip()]
    if not steps:
        raise ValueError(f"{option_name} must contain at least one numeric step.")
    return steps


def _parse_sensitivity_int_steps(raw: str, option_name: str) -> list[int]:
    values: list[int] = []
    for part in _split_sensitivity_steps(raw, option_name):
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(
                f"{option_name} step {part!r} must be an integer."
            ) from exc
        if value < 0:
            raise ValueError(f"{option_name} steps must be non-negative.")
        values.append(value)
    return values


def _parse_sensitivity_float_steps(raw: str, option_name: str) -> list[float]:
    values: list[float] = []
    for part in _split_sensitivity_steps(raw, option_name):
        try:
            value = float(part)
        except ValueError as exc:
            raise ValueError(f"{option_name} step {part!r} must be numeric.") from exc
        if value < 0.0:
            raise ValueError(f"{option_name} steps must be non-negative.")
        values.append(value)
    return values


SensitivitySteps = tuple[list[int], list[float], list[int]]


def _parse_sensitivity_step_options(
    *,
    power_steps_raw: str,
    wind_steps_raw: str,
    battery_steps_raw: str,
) -> SensitivitySteps:
    return (
        _parse_sensitivity_int_steps(
            power_steps_raw,
            "--sensitivity-power-steps",
        ),
        _parse_sensitivity_float_steps(
            wind_steps_raw,
            "--sensitivity-wind-steps",
        ),
        _parse_sensitivity_int_steps(
            battery_steps_raw,
            "--sensitivity-battery-steps",
        ),
    )


def _render_estimate_sensitivity_output(
    *,
    mission_model: MissionPlan,
    vehicle_model: VehicleProfile,
    result: MissionEstimate,
    mission_assets: MissionAssetBundle,
    mission_stem: str,
    wind_provider: WindProvider | None,
    options: EstimationOptions,
    power_steps_raw: str,
    wind_steps_raw: str,
    battery_steps_raw: str,
) -> str:
    try:
        power_steps, wind_steps, battery_steps = _parse_sensitivity_step_options(
            power_steps_raw=power_steps_raw,
            wind_steps_raw=wind_steps_raw,
            battery_steps_raw=battery_steps_raw,
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="estimate",
            code=cli.CliExitCode.INVALID_INPUT,
        )

    levels = run_sensitivity_sweep(
        mission_model,
        vehicle_model,
        power_steps=power_steps,
        wind_steps=wind_steps,
        battery_steps=battery_steps,
        wind_provider=wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        population_provider=mission_assets.population_provider,
        obstacle_provider=mission_assets.obstacle_provider,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
        options=options,
    )
    return render_sensitivity_markdown(
        result,
        levels,
        mission_id=mission_assets.mission_id or mission_stem,
    )


EstimateOutputRenderer = Callable[
    [EstimatorResultEnvelope, MissionEstimate, MissionAssetBundle], str
]


def _render_estimate_profile_output(
    envelope: EstimatorResultEnvelope,
    _result: MissionEstimate,
    mission_assets: MissionAssetBundle,
) -> str:
    return render_profile_markdown(
        envelope, terrain_provider=mission_assets.terrain_provider
    )


def _render_estimate_geojson_output(
    _envelope: EstimatorResultEnvelope,
    result: MissionEstimate,
    mission_assets: MissionAssetBundle,
) -> str:
    return build_geojson_export(
        result,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
        obstacles=mission_assets.obstacle_provider.obstacles()
        if mission_assets.obstacle_provider is not None
        else None,
    )


def _render_estimate_kml_output(
    _envelope: EstimatorResultEnvelope,
    result: MissionEstimate,
    mission_assets: MissionAssetBundle,
) -> str:
    return build_kml_export(
        result,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )


_ESTIMATE_OUTPUT_RENDERERS: dict[OutputFormat, EstimateOutputRenderer] = {
    OutputFormat.PROFILE: _render_estimate_profile_output,
    OutputFormat.GEOJSON: _render_estimate_geojson_output,
    OutputFormat.KML: _render_estimate_kml_output,
}


def _render_estimate_command_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
    result: MissionEstimate,
    mission_assets: MissionAssetBundle,
) -> str:
    renderer = _ESTIMATE_OUTPUT_RENDERERS.get(output_format)
    if renderer is None:
        return _render_output(
            output_format, envelope, mission_id=mission_assets.mission_id
        )
    return renderer(envelope, result, mission_assets)


def _render_estimate_error_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
) -> str:
    if output_format == OutputFormat.SENSITIVITY:
        return _render_output(OutputFormat.JSON, envelope)
    return _render_output(_envelope_output_format(output_format), envelope)


def _exit_code_for_result(result: MissionEstimate) -> cli.CliExitCode:
    if result.status == EstimateStatus.SUCCESS:
        return cli.CliExitCode.SUCCESS
    failure = result.failure
    if failure is None:
        return cli.CliExitCode.INTERNAL_ERROR
    return _FAILURE_KIND_EXIT_CODES.get(failure.kind, cli.CliExitCode.INVALID_INPUT)


def _write_internal_error_envelope(
    *,
    error: Exception,
    output_format: OutputFormat,
    output: Path | None,
    inputs: EnvelopeInputs | None,
    retry_requested_output: bool,
) -> None:
    envelope = build_internal_error_envelope(error=error, inputs=inputs)
    rendered = _render_estimate_error_output(output_format, envelope)

    if retry_requested_output and output is not None:
        try:
            _write_output(rendered, output)
            return
        except OutputWriteError:
            pass

    if retry_requested_output or output is not None:
        try:
            _write_output(rendered, None)
            return
        except OutputWriteError:
            pass

    typer.echo("Failed to write estimator output.", err=True)


def estimate(
    mission: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="Path to mission.v6 YAML file."),
    vehicle: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="Path to vehicle profile YAML file."),
    format: OutputFormat = typer.Option(
        OutputFormat.JSON,
        "--format",
        help="Output format. Use summary for a one-line result, checklist for pre-flight go/no-go, sensitivity for a reserve sweep, or ground-risk for SORA iGRC.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write output to file instead of stdout."),
    calibration: Path | None = typer.Option(
        None,
        "--calibration",
        exists=True,
        readable=True,
        resolve_path=True,
        help=(
            "Optional calibration-profile.v1 JSON to layer on the vehicle. "
            "Overrides matching performance fields; must reference this vehicle_id."
        ),
    ),
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
    sensitivity_power_steps: str = typer.Option(
        "10,20,30",
        "--sensitivity-power-steps",
        help="Comma-separated cruise-power percent steps for --format sensitivity.",
    ),
    sensitivity_wind_steps: str = typer.Option(
        "1,2,3",
        "--sensitivity-wind-steps",
        help="Comma-separated headwind m/s steps for --format sensitivity.",
    ),
    sensitivity_battery_steps: str = typer.Option(
        "10,20,30",
        "--sensitivity-battery-steps",
        help="Comma-separated battery-capacity percent steps for --format sensitivity.",
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate mission and vehicle files against their schemas and exit "
            "without running the estimator. "
            "Exits 0 when both files are valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Run deterministic mission estimation and static feasibility checks."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    envelope_inputs: EnvelopeInputs | None = None
    try:
        options = _build_estimation_options(fidelity, max_segment_length_m)
        wind_provider = (
            LayeredWindProvider(_parse_wind_layers(wind_layer)) if wind_layer else None
        )
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        if calibration is not None:
            vehicle_model = load_and_apply_calibration(vehicle_model, calibration)
        if validate_only:
            typer.echo(f"mission: {mission.name}: OK")
            typer.echo(f"vehicle: {vehicle.name}: OK")
            raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
        mission_assets.mission_id = mission_model.mission_id
        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        if wind_provider is None:
            wind_provider = mission_assets.wind_provider
        envelope_inputs = mission_assets.envelope_inputs(
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        result = cli.try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            options=options,
            wind_provider=wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            population_provider=mission_assets.population_provider,
            obstacle_provider=mission_assets.obstacle_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        envelope = build_estimator_envelope(
            result=result,
            inputs=envelope_inputs,
        )
        if format == OutputFormat.SENSITIVITY:
            rendered = _render_estimate_sensitivity_output(
                mission_model=mission_model,
                vehicle_model=vehicle_model,
                result=result,
                mission_assets=mission_assets,
                mission_stem=mission.stem,
                wind_provider=wind_provider,
                options=options,
                power_steps_raw=sensitivity_power_steps,
                wind_steps_raw=sensitivity_wind_steps,
                battery_steps_raw=sensitivity_battery_steps,
            )
        else:
            rendered = _render_estimate_command_output(
                format,
                envelope,
                result,
                mission_assets,
            )
        _write_output(rendered, output)
        raise typer.Exit(code=int(_exit_code_for_result(result)))
    except InputLoadError as exc:
        envelope = build_invalid_input_envelope(
            error=exc,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        try:
            _write_output(_render_estimate_error_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _write_internal_error_envelope(
                error=write_exc,
                output_format=format,
                output=output,
                inputs=envelope_inputs,
                retry_requested_output=False,
            )
            raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT)) from exc
    except (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError) as exc:
        result = _empty_failed_result(exc.failure)
        asset_error_inputs = _envelope_inputs_for_static_asset_error(
            exc,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            mission_assets=mission_assets,
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
            _write_output(_render_estimate_error_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _write_internal_error_envelope(
                error=write_exc,
                output_format=format,
                output=output,
                inputs=envelope_inputs,
                retry_requested_output=False,
            )
            raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(_exit_code_for_result(result))) from exc
    except OutputWriteError as exc:
        _write_internal_error_envelope(
            error=exc,
            output_format=format,
            output=output,
            inputs=envelope_inputs,
            retry_requested_output=False,
        )
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
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
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
