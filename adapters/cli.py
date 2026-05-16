"""Typer CLI adapter for estimator execution."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TypeVar

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
from adapters.sitl_comparison import render_sitl_comparison_json
from adapters.sitl_comparison_markdown import render_sitl_comparison_markdown
from adapters.sitl_evidence import (
    build_sitl_evidence_bundle,
    compare_sitl_evidence_bundle,
    render_sitl_evidence_json,
)
from adapters.sitl_evidence_io import load_sitl_evidence_bundle
from adapters.terrain_grid import TerrainGridLoadError, load_terrain_grid
from adapters.uncertainty_envelope import (
    UncertaintyResultEnvelope,
    build_uncertainty_envelope,
    render_uncertainty_envelope_json,
)
from adapters.uncertainty_io import (
    load_uncertainty_plan,
    resolve_uncertainty_asset_path,
)
from adapters.uncertainty_markdown import render_uncertainty_markdown
from adapters.wind_grid import WindGridLoadError, load_wind_grid
from estimator import (
    EstimateStatus,
    EstimationOptions,
    EstimatorFailure,
    FailureKind,
    FidelityMode,
    GeofenceZone,
    GridTerrainProvider,
    LayeredWindProvider,
    LandingZone,
    MissionEstimate,
    ScenarioResult,
    ScenarioStatus,
    SpatiotemporalWindProvider,
    WindLayer,
    run_scenario,
    try_estimate_mission_distance_time,
)
from estimator.execution.monte_carlo import run_monte_carlo
from schemas import MissionPlan, ScenarioPlan, VehicleProfile

GeoJsonAssetLoadError = GeofenceLoadError | LandingZoneLoadError
LoadedAssetT = TypeVar("LoadedAssetT")

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


_FAILURE_KIND_EXIT_CODES = {
    FailureKind.INFEASIBLE: CliExitCode.INFEASIBLE,
    FailureKind.UNSUPPORTED: CliExitCode.UNSUPPORTED,
}
_FAILURE_KIND_STATUSES = {
    FailureKind.INFEASIBLE: EstimateStatus.INFEASIBLE,
}


class OutputWriteError(OSError):
    """Raised when the CLI cannot write rendered output."""


@dataclass
class MissionAssetBundle:
    """Loaded optional mission assets plus their input provenance."""

    terrain_provider: GridTerrainProvider | None = None
    terrain_document: InputDocument | None = None
    wind_provider: SpatiotemporalWindProvider | None = None
    wind_grid_document: InputDocument | None = None
    geofences: list[GeofenceZone] | None = None
    geofence_document: InputDocument | None = None
    landing_zones: list[LandingZone] | None = None
    landing_zone_document: InputDocument | None = None

    def envelope_inputs(
        self,
        *,
        mission_document: InputDocument,
        vehicle_document: InputDocument,
    ) -> EnvelopeInputs:
        return EnvelopeInputs(
            mission=mission_document,
            vehicle=vehicle_document,
            geofences=self.geofence_document,
            landing_zones=self.landing_zone_document,
            terrain=self.terrain_document,
            wind_grid=self.wind_grid_document,
        )

    def known_documents(self) -> dict[str, InputDocument | None]:
        return {
            "geofences": self.geofence_document,
            "landing_zones": self.landing_zone_document,
            "terrain": self.terrain_document,
            "wind_grid": self.wind_grid_document,
        }


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


def _render_uncertainty_output(
    output_format: OutputFormat,
    envelope: UncertaintyResultEnvelope,
) -> str:
    if output_format == OutputFormat.MARKDOWN:
        return render_uncertainty_markdown(envelope)
    return render_uncertainty_envelope_json(envelope)


def _render_sitl_comparison_output(
    output_format: OutputFormat,
    bundle_path: Path,
    *,
    comparison_id: str | None,
    position_tolerance_m: float,
) -> str:
    bundle, _document = load_sitl_evidence_bundle(bundle_path)
    try:
        report = compare_sitl_evidence_bundle(
            bundle,
            comparison_id=comparison_id or f"{bundle.evidence_id}-comparison",
            position_tolerance_m=position_tolerance_m,
        )
    except ValidationError as exc:
        raise InputLoadError(
            "SITL comparison report failed schema validation.",
            input_name="sitl_comparison",
            path=Path("--comparison-id"),
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
        ) from exc

    if output_format == OutputFormat.MARKDOWN:
        return render_sitl_comparison_markdown(report)
    return render_sitl_comparison_json(report)


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
    failure = result.failure
    if failure is None:
        return CliExitCode.INTERNAL_ERROR
    return _FAILURE_KIND_EXIT_CODES.get(failure.kind, CliExitCode.INVALID_INPUT)


def _status_for_failure_kind(kind: FailureKind) -> EstimateStatus:
    return _FAILURE_KIND_STATUSES.get(kind, EstimateStatus.ERROR)


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


def _load_optional_asset(
    path: Path | None,
    *,
    mission_path: Path,
    loader: Callable[[Path], tuple[LoadedAssetT, InputDocument]],
) -> tuple[LoadedAssetT | None, InputDocument | None]:
    if path is None:
        return None, None
    return loader(_resolve_asset_path(path, mission_path=mission_path))


def _populate_mission_assets(
    bundle: MissionAssetBundle,
    *,
    mission_model: MissionPlan,
    mission_document: InputDocument,
) -> None:
    mission_path = mission_document.path
    bundle.terrain_provider, bundle.terrain_document = _load_optional_asset(
        mission_model.assets.terrain_file,
        mission_path=mission_path,
        loader=load_terrain_grid,
    )
    bundle.wind_provider, bundle.wind_grid_document = _load_optional_asset(
        mission_model.assets.wind_grid_file,
        mission_path=mission_path,
        loader=load_wind_grid,
    )
    bundle.geofences, bundle.geofence_document = _load_optional_asset(
        mission_model.assets.geofences_file,
        mission_path=mission_path,
        loader=load_geofences,
    )
    bundle.landing_zones, bundle.landing_zone_document = _load_optional_asset(
        mission_model.assets.landing_zones_file,
        mission_path=mission_path,
        loader=load_landing_zones,
    )


def _envelope_inputs_for_static_asset_error(
    error: GeoJsonAssetLoadError,
    *,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
    mission_assets: MissionAssetBundle,
) -> EnvelopeInputs | None:
    if mission_document is None or vehicle_document is None:
        return None

    return EnvelopeInputs(
        mission=mission_document,
        vehicle=vehicle_document,
        geofences=(
            error.document
            if isinstance(error, GeofenceLoadError)
            else mission_assets.geofence_document
        ),
        landing_zones=(
            error.document
            if isinstance(error, LandingZoneLoadError)
            else mission_assets.landing_zone_document
        ),
        terrain=mission_assets.terrain_document,
        wind_grid=mission_assets.wind_grid_document,
    )


def _input_error_for_geojson_asset_error(
    error: GeofenceLoadError | LandingZoneLoadError,
) -> InputLoadError:
    input_name = (
        "geofences" if isinstance(error, GeofenceLoadError) else "landing_zones"
    )
    return InputLoadError(
        str(error),
        input_name=input_name,
        path=error.path,
        stage=InputLoadStage.SCHEMA_VALIDATION,
        details=error.failure.context,
        document=error.document,
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
def estimate(
    mission: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    vehicle: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    sitl_evidence: Path | None = typer.Option(
        None,
        "--sitl-evidence",
        exists=True,
        readable=True,
        resolve_path=True,
        help=(
            "Render a SITL comparison report from an existing sitl-evidence.v1 "
            "bundle instead of an estimator envelope."
        ),
    ),
    comparison_id: str | None = typer.Option(
        None,
        "--comparison-id",
        help="Comparison report identifier when --sitl-evidence is provided.",
    ),
    position_tolerance_m: float = typer.Option(
        500.0,
        "--position-tolerance-m",
        min=0.0,
        help="Position proximity tolerance in metres for SITL comparison reports.",
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
) -> None:
    """Run the estimator or render a SITL comparison from evidence."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    envelope_inputs: EnvelopeInputs | None = None
    try:
        if sitl_evidence is not None:
            _write_output(
                _render_sitl_comparison_output(
                    format,
                    sitl_evidence,
                    comparison_id=comparison_id,
                    position_tolerance_m=position_tolerance_m,
                ),
                output,
            )
            raise typer.Exit(code=int(CliExitCode.SUCCESS))

        options = _build_estimation_options(fidelity, max_segment_length_m)
        wind_provider = (
            LayeredWindProvider(_parse_wind_layers(wind_layer)) if wind_layer else None
        )
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
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


def _resolve_scenario_input_paths(
    scenario_plan: ScenarioPlan,
    *,
    scenario_file: Path,
) -> tuple[Path, Path]:
    return (
        resolve_scenario_asset_path(
            scenario_plan.mission_file,
            scenario_path=scenario_file,
        ),
        resolve_scenario_asset_path(
            scenario_plan.vehicle_file,
            scenario_path=scenario_file,
        ),
    )


def _run_scenario_with_assets(
    *,
    scenario_plan: ScenarioPlan,
    mission_model: MissionPlan,
    vehicle_model: VehicleProfile,
    mission_assets: MissionAssetBundle,
) -> ScenarioResult:
    return run_scenario(
        scenario_plan,
        mission_model,
        vehicle_model,
        wind_provider=mission_assets.wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )


def _build_scenario_result_envelope(
    *,
    result: ScenarioResult,
    scenario_document: InputDocument,
    mission_document: InputDocument,
    vehicle_document: InputDocument,
    mission_assets: MissionAssetBundle,
) -> ScenarioResultEnvelope:
    return build_scenario_envelope(
        result=result,
        scenario_document=scenario_document,
        mission_document=mission_document,
        vehicle_document=vehicle_document,
        geofence_document=mission_assets.geofence_document,
        landing_zone_document=mission_assets.landing_zone_document,
        terrain_document=mission_assets.terrain_document,
        wind_grid_document=mission_assets.wind_grid_document,
    )


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
) -> None:
    """Run the deterministic scenario runner and emit a scenario result envelope."""

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
        _write_output(_render_scenario_output(format, envelope), output)
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


@app.command()
def sample(
    uncertainty_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    format: OutputFormat = typer.Option(OutputFormat.JSON, "--format"),
    output: Path | None = typer.Option(None, "--output", "-o"),
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
        _write_output(_render_uncertainty_output(format, envelope), output)
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        typer.echo(f"Input error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(f"Output write error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Internal error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc


@app.command()
def sitl(
    scenario_file: Path = typer.Argument(
        ..., exists=True, readable=True, resolve_path=True
    ),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Build a contract-only SITL evidence bundle for an existing scenario."""

    try:
        scenario_plan, scenario_document = load_scenario(scenario_file)
        mission_path, vehicle_path = _resolve_scenario_input_paths(
            scenario_plan,
            scenario_file=scenario_file,
        )
        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)
        mission_assets = MissionAssetBundle()
        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        scenario_result = _run_scenario_with_assets(
            scenario_plan=scenario_plan,
            mission_model=mission_model,
            vehicle_model=vehicle_model,
            mission_assets=mission_assets,
        )
        scenario_envelope = _build_scenario_result_envelope(
            result=scenario_result,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            mission_assets=mission_assets,
        )
        evidence = build_sitl_evidence_bundle(
            evidence_id=f"{scenario_plan.scenario_id}-sitl-contract",
            scenario_envelope=scenario_envelope,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            vehicle=vehicle_model,
            geofence_document=mission_assets.geofence_document,
            landing_zone_document=mission_assets.landing_zone_document,
            terrain_document=mission_assets.terrain_document,
            wind_grid_document=mission_assets.wind_grid_document,
        )
        _write_output(render_sitl_evidence_json(evidence), output)
        raise typer.Exit(code=int(CliExitCode.SUCCESS))
    except InputLoadError as exc:
        typer.echo(f"Input error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except (
        GeofenceLoadError,
        LandingZoneLoadError,
        TerrainGridLoadError,
        WindGridLoadError,
    ) as exc:
        typer.echo(f"Input error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(f"Output write error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Internal error: {exc}", err=True)
        raise typer.Exit(code=int(CliExitCode.INTERNAL_ERROR)) from exc
