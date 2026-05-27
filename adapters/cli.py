"""Typer CLI adapter for estimator execution."""

import json
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import NoReturn, Protocol

import typer
from pydantic import ValidationError

from adapters.sitl.ardupilot_types import ArduPilotAdapterError
from adapters.batch_io import load_batch_manifest
from adapters.batch_support import (
    render_batch_csv,
    render_batch_table,
    run_batch_manifest,
)
from adapters.battery_sizer import (
    BatterySizingResult,
    compute_minimum_battery_capacity,
    render_battery_sizing_markdown,
    render_battery_sizing_summary,
)
from adapters.battery_sizing_envelope import (
    BatterySizingEnvelope,
    build_battery_sizing_envelope,
    render_battery_sizing_envelope_json,
)
from adapters.cli_batch_support import (
    _batch_exit_code,
    write_batch_outputs,
)
from adapters.cli_sitl_support import (
    _build_sitl_evidence_from_context,
    _emit_sitl_progress,
    _exit_code_for_comparison_report,
    _load_sitl_scenario_context,
    _render_sitl_comparison_output,
    _render_sitl_evidence_output,
    _resolve_sitl_live_options,
    _sitl_adapter_for_options,
)
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _build_estimation_options,
    _build_scenario_result_envelope,
    _empty_failed_result,
    _envelope_inputs_for_static_asset_error,
    _envelope_output_format,
    _input_error_for_geojson_asset_error,
    _parse_wind_layers,
    _populate_mission_assets,
    _render_output,
    _render_scenario_output,
    _render_stochastic_output,
    _render_uncertainty_output,
    _resolve_scenario_input_paths,
    _run_scenario_with_assets,
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
from adapters.geofence_geojson import GeofenceLoadError
from adapters.geojson_export import build_geojson_export
from adapters.profile_markdown import (
    render_profile_markdown,
    render_profile_markdown_from_scenario,
)
from adapters.sensitivity import render_sensitivity_markdown, run_sensitivity_sweep
from adapters.io import (
    InputDocument,
    InputLoadError,
    load_mission,
    load_vehicle,
)
from adapters.kml_export import build_kml_export
from adapters.landing_zone_geojson import LandingZoneLoadError
from adapters.qgc_plan import load_and_convert_plan
from adapters.scenario_envelope import (
    ScenarioResultEnvelope,
    build_scenario_internal_error_envelope,
    build_scenario_invalid_input_envelope,
)
from adapters.scenario_io import load_scenario
from adapters.sitl.evidence import compare_sitl_evidence_bundle
from adapters.sitl.evidence_io import load_sitl_evidence_bundle
from adapters.stochastic_envelope import build_stochastic_envelope
from adapters.stochastic_io import (
    load_stochastic_plan,
    resolve_stochastic_asset_path,
)
from adapters.terrain_grid import TerrainGridLoadError
from adapters.uncertainty_envelope import (
    build_uncertainty_envelope,
)
from adapters.uncertainty_io import (
    load_uncertainty_plan,
    resolve_uncertainty_asset_path,
)
from adapters.wind_grid import WindGridLoadError
from estimator import (
    EstimateStatus,
    FailureKind,
    FidelityMode,
    GeofenceZone,
    LandingZone,
    LayeredWindProvider,
    MissionEstimate,
    ScenarioResult,
    ScenarioStatus,
    try_estimate_mission_distance_time,
)
from estimator.execution.monte_carlo import run_monte_carlo
from estimator.execution.propagator import run_stochastic_propagation

app = typer.Typer(name="bvlos-sim", add_completion=False, no_args_is_help=True)

_VERSION = "0.22.0"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bvlos-sim {_VERSION}")
        raise typer.Exit()


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


class DocumentOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class SummaryOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"


class BatchOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"
    GEOJSON = "geojson"
    KML = "kml"
    CHECKLIST = "checklist"
    PROFILE = "profile"
    CSV = "csv"


class BatterySizingOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    SUMMARY = "summary"


_DOCUMENT_OUTPUT_FORMATS: dict[DocumentOutputFormat, OutputFormat] = {
    DocumentOutputFormat.JSON: OutputFormat.JSON,
    DocumentOutputFormat.MARKDOWN: OutputFormat.MARKDOWN,
}

_SUMMARY_OUTPUT_FORMATS: dict[SummaryOutputFormat, OutputFormat] = {
    SummaryOutputFormat.JSON: OutputFormat.JSON,
    SummaryOutputFormat.MARKDOWN: OutputFormat.MARKDOWN,
    SummaryOutputFormat.SUMMARY: OutputFormat.SUMMARY,
}
_FAILURE_KIND_EXIT_CODES = {
    FailureKind.INFEASIBLE: CliExitCode.INFEASIBLE,
    FailureKind.UNSUPPORTED: CliExitCode.UNSUPPORTED,
}


class RouteExportBuilder(Protocol):
    def __call__(
        self,
        estimate: MissionEstimate,
        *,
        geofence_zones: list[GeofenceZone] | None = None,
        landing_zones: list[LandingZone] | None = None,
    ) -> str: ...


_ROUTE_EXPORT_BUILDERS: dict[OutputFormat, RouteExportBuilder] = {
    OutputFormat.GEOJSON: build_geojson_export,
    OutputFormat.KML: build_kml_export,
}


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """BVLOS simulator command group."""


def _render_cli_error(
    message: str,
    command: str,
    *,
    details: dict | None = None,
) -> str:
    payload: dict = {"command": command, "status": "error", "message": message}
    if details:
        payload["details"] = details
    return json.dumps(payload, indent=2) + "\n"


def _exit_with_cli_error(
    message: str,
    *,
    command: str,
    code: CliExitCode,
    details: dict | None = None,
) -> NoReturn:
    typer.echo(_render_cli_error(message, command, details=details), nl=False)
    raise typer.Exit(code=int(code))


def _document_output_format(output_format: DocumentOutputFormat) -> OutputFormat:
    return _DOCUMENT_OUTPUT_FORMATS[output_format]


def _summary_output_format(output_format: SummaryOutputFormat) -> OutputFormat:
    return _SUMMARY_OUTPUT_FORMATS[output_format]


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


def _validate_battery_sizing_margins(
    margins: list[int] | None,
) -> list[int] | None:
    if margins is None:
        return None
    if any(margin < 0 for margin in margins):
        raise ValueError("--margin values must be non-negative.")
    return list(margins)


def _render_estimate_command_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
    result: MissionEstimate,
    mission_assets: MissionAssetBundle,
) -> str:
    if output_format == OutputFormat.PROFILE:
        return render_profile_markdown(
            envelope, terrain_provider=mission_assets.terrain_provider
        )
    builder = _ROUTE_EXPORT_BUILDERS.get(output_format)
    if builder is None:
        return _render_output(
            output_format, envelope, mission_id=mission_assets.mission_id
        )
    return builder(
        result,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )


def _render_estimate_error_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
) -> str:
    if output_format == OutputFormat.SENSITIVITY:
        return _render_output(OutputFormat.JSON, envelope)
    return _render_output(_envelope_output_format(output_format), envelope)


def _render_scenario_command_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
    result: ScenarioResult,
    mission_assets: MissionAssetBundle,
) -> str:
    if output_format == OutputFormat.PROFILE:
        return render_profile_markdown_from_scenario(
            envelope, terrain_provider=mission_assets.terrain_provider
        )
    builder = _ROUTE_EXPORT_BUILDERS.get(output_format)
    if builder is None:
        return _render_scenario_output(output_format, envelope)
    if result.estimate is None:
        return _render_scenario_output(OutputFormat.JSON, envelope)
    return builder(
        result.estimate,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )


def _render_scenario_error_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
) -> str:
    return _render_scenario_output(_envelope_output_format(output_format), envelope)


def _render_battery_sizing_command_output(
    output_format: BatterySizingOutputFormat,
    envelope: BatterySizingEnvelope,
    result: BatterySizingResult,
    *,
    mission_id: str,
    safety_margins: list[int] | None,
) -> str:
    if output_format == BatterySizingOutputFormat.JSON:
        return render_battery_sizing_envelope_json(envelope)
    if output_format == BatterySizingOutputFormat.MARKDOWN:
        return render_battery_sizing_markdown(
            result,
            mission_id=mission_id,
            safety_margins=safety_margins,
        )
    return render_battery_sizing_summary(
        result,
        safety_margins=safety_margins,
    )


def _exit_code_for_result(result: MissionEstimate) -> CliExitCode:
    if result.status == EstimateStatus.SUCCESS:
        return CliExitCode.SUCCESS
    failure = result.failure
    if failure is None:
        return CliExitCode.INTERNAL_ERROR
    return _FAILURE_KIND_EXIT_CODES.get(failure.kind, CliExitCode.INVALID_INPUT)


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

    # For unexpected exceptions, retry the originally requested output path first.
    if retry_requested_output and output is not None:
        try:
            _write_output(rendered, output)
            return
        except OutputWriteError:
            pass

    # Fall back to stdout: either output was stdout all along (output=None,
    # retry=True), or a file write failed and we degrade to stdout.
    if retry_requested_output or output is not None:
        try:
            _write_output(rendered, None)
            return
        except OutputWriteError:
            pass

    typer.echo("Failed to write estimator output.", err=True)


@app.command()
def convert(
    plan: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Convert a QGroundControl .plan file to a mission.v5 YAML."""

    import yaml

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
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except (json.JSONDecodeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc


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
        if validate_only:
            typer.echo(f"mission: {mission.name}: OK")
            typer.echo(f"vehicle: {vehicle.name}: OK")
            raise typer.Exit(code=int(CliExitCode.SUCCESS))
        mission_assets.mission_id = mission_model.mission_id
        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        # CLI --wind-layer takes precedence over mission asset wind grid
        if wind_provider is None:
            wind_provider = mission_assets.wind_provider
        envelope_inputs = mission_assets.envelope_inputs(
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        result = try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            options=options,
            wind_provider=wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        envelope = build_estimator_envelope(
            result=result,
            inputs=envelope_inputs,
        )
        if format == OutputFormat.SENSITIVITY:
            try:
                power_steps = _parse_sensitivity_int_steps(
                    sensitivity_power_steps,
                    "--sensitivity-power-steps",
                )
                wind_steps = _parse_sensitivity_float_steps(
                    sensitivity_wind_steps,
                    "--sensitivity-wind-steps",
                )
                battery_steps = _parse_sensitivity_int_steps(
                    sensitivity_battery_steps,
                    "--sensitivity-battery-steps",
                )
            except ValueError as exc:
                _exit_with_cli_error(
                    str(exc),
                    command="estimate",
                    code=CliExitCode.INVALID_INPUT,
                )
            levels = run_sensitivity_sweep(
                mission_model,
                vehicle_model,
                power_steps=power_steps,
                wind_steps=wind_steps,
                battery_steps=battery_steps,
                wind_provider=wind_provider,
                terrain_provider=mission_assets.terrain_provider,
                geofences=mission_assets.geofences,
                landing_zones=mission_assets.landing_zones,
                options=options,
            )
            rendered = render_sensitivity_markdown(
                result,
                levels,
                mission_id=mission_assets.mission_id or mission.stem,
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
            raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from write_exc
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except (GeofenceLoadError, LandingZoneLoadError) as exc:
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


@app.command("size-battery")
def size_battery(
    mission: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    vehicle: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    format: BatterySizingOutputFormat = typer.Option(
        BatterySizingOutputFormat.MARKDOWN,
        "--format",
    ),
    output: Path | None = typer.Option(None, "--output", "-o"),
    margin: list[int] | None = typer.Option(
        None,
        "--margin",
        help="Safety margin percent. Repeat to show multiple recommendations.",
    ),
) -> None:
    """Compute minimum battery capacity needed for mission feasibility."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    envelope_inputs: EnvelopeInputs | None = None
    mission_assets = MissionAssetBundle()
    try:
        safety_margins = _validate_battery_sizing_margins(margin)
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        mission_assets.mission_id = mission_model.mission_id
        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        envelope_inputs = mission_assets.envelope_inputs(
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        result = compute_minimum_battery_capacity(
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        mission_id = mission_assets.mission_id or mission.stem
        envelope = build_battery_sizing_envelope(
            result=result,
            mission_id=mission_id,
            inputs=envelope_inputs,
        )
        rendered = _render_battery_sizing_command_output(
            format,
            envelope,
            result,
            mission_id=mission_id,
            safety_margins=safety_margins,
        )
        _write_output(rendered, output)
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        _exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except (GeofenceLoadError, LandingZoneLoadError, TerrainGridLoadError, WindGridLoadError) as exc:
        _exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=CliExitCode.INVALID_INPUT,
        )
    except ValueError as exc:
        _exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        _exit_with_cli_error(
            "Unable to write size-battery output.",
            command="size-battery",
            code=CliExitCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__},
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _exit_with_cli_error(
            "Unexpected internal error while running size-battery.",
            command="size-battery",
            code=CliExitCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__},
        )


@app.command()
def batch(
    manifest: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    format: BatchOutputFormat = typer.Option(BatchOutputFormat.SUMMARY, "--format"),
) -> None:
    """Run batch mission estimates from a batch.v1 manifest file."""

    try:
        batch_manifest = load_batch_manifest(manifest)
        results = run_batch_manifest(batch_manifest)
        for result in results:
            if result.error_message is None:
                continue
            typer.echo(f"Warning: run {result.id}: {result.error_message}", err=True)
        if format == BatchOutputFormat.CSV:
            _write_output(render_batch_csv(results), None)
        else:
            if output_dir is not None:
                write_batch_outputs(
                    output_dir=output_dir,
                    output_format=OutputFormat(format),
                    results=results,
                )
            _write_output(render_batch_table(results), None)
        raise typer.Exit(code=_batch_exit_code(results))
    except InputLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc


@app.command()
def compare(
    evidence: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to a sitl-evidence.v1 JSON bundle.",
    ),
    comparison_id: str | None = typer.Option(
        None,
        "--comparison-id",
        help="Stable comparison report identifier. Defaults to <evidence_id>-comparison.",
    ),
    position_tolerance_m: float = typer.Option(
        500.0,
        "--position-tolerance-m",
        min=0.0,
        help="Position proximity tolerance in metres.",
    ),
    format: DocumentOutputFormat = typer.Option(DocumentOutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Compare a SITL evidence bundle against its embedded scenario expectations."""

    try:
        bundle, _document = load_sitl_evidence_bundle(evidence)
        report = compare_sitl_evidence_bundle(
            bundle,
            comparison_id=comparison_id or f"{bundle.evidence_id}-comparison",
            position_tolerance_m=position_tolerance_m,
        )
        _write_output(
            _render_sitl_comparison_output(_document_output_format(format), report),
            output,
        )
        raise typer.Exit(code=int(_exit_code_for_comparison_report(report)))
    except InputLoadError as exc:
        _exit_with_cli_error(
            str(exc),
            command="compare",
            code=CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        _exit_with_cli_error(
            f"comparison_id: {first['msg']}",
            command="compare",
            code=CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        _exit_with_cli_error(
            str(exc),
            command="compare",
            code=CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _exit_with_cli_error(
            str(exc),
            command="compare",
            code=CliExitCode.INTERNAL_ERROR,
        )


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
    _write_output(_render_scenario_error_output(output_format, internal_envelope), None)


def _scenario_exit_code_for_result(result: ScenarioResult) -> ScenarioExitCode:
    if result.status == ScenarioStatus.PASSED:
        return ScenarioExitCode.PASSED
    return ScenarioExitCode.FAILED


@app.command()
def scenario(
    scenario_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate scenario, mission, and vehicle files against their schemas "
            "and exit without running the scenario. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
) -> None:
    """Run the deterministic scenario runner and emit a scenario result envelope."""

    if format == OutputFormat.SENSITIVITY:
        _exit_with_cli_error(
            "--format sensitivity is only supported by estimate.",
            command="scenario",
            code=CliExitCode.INVALID_INPUT,
        )

    scenario_document: InputDocument | None = None
    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    scenario_id = "<unknown>"

    try:
        scenario_plan, scenario_document = load_scenario(scenario_file)
        scenario_id = scenario_plan.scenario_id

        mission_path, vehicle_path = _resolve_scenario_input_paths(
            scenario_plan,
            scenario_file=scenario_file,
        )
        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)
        if validate_only:
            typer.echo(f"scenario: {scenario_file.name}: OK")
            typer.echo(f"mission: {mission_path.name}: OK")
            typer.echo(f"vehicle: {vehicle_path.name}: OK")
            raise typer.Exit(code=int(CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = _run_scenario_with_assets(
            scenario_plan=scenario_plan,
            mission_model=mission_model,
            vehicle_model=vehicle_model,
            mission_assets=mission_assets,
        )
        envelope = _build_scenario_result_envelope(
            result=result,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            mission_assets=mission_assets,
        )
        _write_output(
            _render_scenario_command_output(format, envelope, result, mission_assets),
            output,
        )
        raise typer.Exit(code=int(_scenario_exit_code_for_result(result)))
    except InputLoadError as exc:
        envelope = build_scenario_invalid_input_envelope(
            scenario_id=scenario_id,
            error=exc,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            known_documents=mission_assets.known_documents(),
        )
        try:
            _write_output(_render_scenario_error_output(format, envelope), output)
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
    except (GeofenceLoadError, LandingZoneLoadError) as exc:
        envelope = build_scenario_invalid_input_envelope(
            scenario_id=scenario_id,
            error=_input_error_for_geojson_asset_error(exc),
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            known_documents=mission_assets.known_documents(),
        )
        try:
            _write_output(_render_scenario_error_output(format, envelope), output)
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


@app.command()
def sample(
    uncertainty_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    format: SummaryOutputFormat = typer.Option(SummaryOutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
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
            raise typer.Exit(code=int(CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = run_monte_carlo(
            plan,
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
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
            _render_uncertainty_output(_summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        _exit_with_cli_error(
            str(exc),
            command="sample",
            code=CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        _exit_with_cli_error(
            str(exc),
            command="sample",
            code=CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        _exit_with_cli_error(
            str(exc),
            command="sample",
            code=CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _exit_with_cli_error(
            str(exc),
            command="sample",
            code=CliExitCode.INTERNAL_ERROR,
        )


@app.command()
def propagate(
    stochastic_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    format: SummaryOutputFormat = typer.Option(SummaryOutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
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
            raise typer.Exit(code=int(CliExitCode.SUCCESS))

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = run_stochastic_propagation(
            plan,
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
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
            _render_stochastic_output(_summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        _exit_with_cli_error(
            str(exc),
            command="propagate",
            code=CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        _exit_with_cli_error(
            str(exc),
            command="propagate",
            code=CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        _exit_with_cli_error(
            str(exc),
            command="propagate",
            code=CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _exit_with_cli_error(
            str(exc),
            command="propagate",
            code=CliExitCode.INTERNAL_ERROR,
        )


@app.command()
def sitl(
    scenario_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    output: Path | None = typer.Option(None, "--output", "-o"),
    format: DocumentOutputFormat = typer.Option(DocumentOutputFormat.JSON, "--format"),
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
) -> None:
    """Build contract-only or live ArduPilot SITL evidence from a scenario."""

    live_options = _resolve_sitl_live_options(
        live=live,
        host=host,
        port=port,
        artifact_dir=artifact_dir,
        telemetry_samples=telemetry_samples,
        telemetry_timeout_s=telemetry_timeout_s,
    )
    if live and live_options is None:
        _exit_with_cli_error(
            "--artifact-dir is required when --live is specified.",
            command="sitl",
            code=CliExitCode.INVALID_INPUT,
        )
    try:
        context = _load_sitl_scenario_context(scenario_file)
        adapter = _sitl_adapter_for_options(context, live_options)
        if live_options is not None:
            _emit_sitl_progress("Writing evidence bundle...")
        evidence = _build_sitl_evidence_from_context(
            context,
            adapter=adapter,
            live_options=live_options,
        )
        _write_output(
            _render_sitl_evidence_output(_document_output_format(format), evidence),
            output,
        )
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        _exit_with_cli_error(
            str(exc),
            command="sitl",
            code=CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except (
        GeofenceLoadError,
        LandingZoneLoadError,
        TerrainGridLoadError,
        WindGridLoadError,
    ) as exc:
        _exit_with_cli_error(
            str(exc),
            command="sitl",
            code=CliExitCode.INVALID_INPUT,
        )
    except ArduPilotAdapterError as exc:
        _exit_with_cli_error(
            f"SITL adapter error: {exc}",
            command="sitl",
            code=CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        _exit_with_cli_error(
            str(exc),
            command="sitl",
            code=CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        _exit_with_cli_error(
            str(exc),
            command="sitl",
            code=CliExitCode.INTERNAL_ERROR,
        )
