"""Shared CLI support for mission assets and scenario execution."""

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, TypeVar

import typer

from pydantic import ValidationError

from adapters.envelope import (
    EnvelopeInputs,
    EstimatorResultEnvelope,
    OutputFormat,
    render_envelope_json,
)
from adapters.atomic_write import AtomicWriteDurabilityError, atomic_write_text
from adapters.assets.geofence_geojson import GeofenceLoadError, load_geofences
from adapters.assets.obstacle_geojson import ObstacleLoadError, load_obstacles
from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    validation_error_summary,
)
from adapters.assets.landing_zone_geojson import (
    LandingZoneLoadError,
    load_landing_zones,
)
from adapters.assets.population_grid import load_population_grid
from adapters.checklist_markdown import (
    render_checklist_markdown,
    render_checklist_markdown_from_scenario,
)
from adapters.ground_risk_markdown import (
    render_ground_risk_markdown,
    render_ground_risk_markdown_from_scenario,
)
from adapters.markdown import render_envelope_markdown
from adapters.scenario_envelope import (
    ScenarioResultEnvelope,
    build_scenario_envelope,
    render_scenario_envelope_json,
)
from adapters.scenario_io import resolve_scenario_asset_path
from adapters.scenario_markdown import render_scenario_markdown
from adapters.stochastic_envelope import (
    StochasticResultEnvelope,
    render_stochastic_envelope_json,
)
from adapters.stochastic_markdown import render_stochastic_markdown
from adapters.summary import (
    format_estimate_summary,
    format_scenario_summary,
    format_stochastic_summary,
    format_uncertainty_summary,
)
from adapters.assets.terrain_grid import load_terrain_grid
from adapters.uncertainty_envelope import (
    UncertaintyResultEnvelope,
    render_uncertainty_envelope_json,
)
from adapters.uncertainty_markdown import render_uncertainty_markdown
from adapters.assets.wind_grid import load_wind_grid
from estimator import (
    EstimateStatus,
    EstimationOptions,
    EstimatorFailure,
    FailureKind,
    FidelityMode,
    GeofenceZone,
    GridPopulationProvider,
    GridTerrainProvider,
    LandingZone,
    ListObstacleProvider,
    MissionEstimate,
    ScenarioResult,
    SpatiotemporalWindProvider,
    WindLayer,
    run_scenario,
)
from schemas import MissionPlan, ScenarioPlan, VehicleProfile

GeoJsonAssetLoadError = GeofenceLoadError | LandingZoneLoadError | ObstacleLoadError
LoadedAssetT = TypeVar("LoadedAssetT")
_MAX_SEGMENT_FLAG = "--max-segment-length-m"
_WIND_LAYER_FLAG = "--wind-layer"
_GENERATED_AT_FLAG = "--generated-at"
_FAILURE_KIND_STATUSES = {
    FailureKind.INFEASIBLE: EstimateStatus.INFEASIBLE,
}

NO_CLOBBER_OPTION = typer.Option(
    False,
    "--no-clobber",
    help=(
        "Refuse to overwrite an existing --output file: exit INVALID_INPUT (11) "
        "with a clear message instead. Default behavior replaces the file atomically."
    ),
)

OPERATOR_ID_OPTION = typer.Option(
    None,
    "--operator-id",
    help=(
        "Operator identity recorded in the result's free-form metadata map. "
        "Omitted entirely when the flag is absent, keeping outputs byte-identical."
    ),
)

GENERATED_AT_OPTION = typer.Option(
    None,
    "--generated-at",
    help=(
        "Generation timestamp recorded in the result's free-form metadata map: "
        "an ISO 8601 timestamp, or 'now' for the current UTC time. "
        "Omitted entirely when the flag is absent, keeping outputs byte-identical."
    ),
)


@dataclass
class MissionAssetBundle:
    """Loaded optional mission assets plus their input provenance."""

    terrain_provider: GridTerrainProvider | None = None
    terrain_document: InputDocument | None = None
    population_provider: GridPopulationProvider | None = None
    population_document: InputDocument | None = None
    obstacle_provider: ListObstacleProvider | None = None
    obstacle_document: InputDocument | None = None
    wind_provider: SpatiotemporalWindProvider | None = None
    wind_grid_document: InputDocument | None = None
    geofences: list[GeofenceZone] | None = None
    geofence_document: InputDocument | None = None
    landing_zones: list[LandingZone] | None = None
    landing_zone_document: InputDocument | None = None
    mission_id: str | None = None

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
            population=self.population_document,
            obstacles=self.obstacle_document,
            wind_grid=self.wind_grid_document,
        )

    def known_documents(self) -> dict[str, InputDocument | None]:
        return {
            "geofences": self.geofence_document,
            "landing_zones": self.landing_zone_document,
            "terrain": self.terrain_document,
            "population": self.population_document,
            "obstacles": self.obstacle_document,
            "wind_grid": self.wind_grid_document,
        }


@dataclass(frozen=True)
class SitlScenarioContext:
    """Loaded scenario inputs and deterministic expected output for SITL."""

    scenario_plan: ScenarioPlan
    scenario_document: InputDocument
    mission_model: MissionPlan
    mission_document: InputDocument
    vehicle_model: VehicleProfile
    vehicle_document: InputDocument
    mission_assets: MissionAssetBundle
    scenario_envelope: ScenarioResultEnvelope


def _resolve_asset_path(path: Path, *, mission_path: Path) -> Path:
    if path.is_absolute():
        return path
    return mission_path.parent / path


EstimatorEnvelopeRenderer = Callable[[EstimatorResultEnvelope], str]
ScenarioEnvelopeRenderer = Callable[[ScenarioResultEnvelope], str]
UncertaintyEnvelopeRenderer = Callable[[UncertaintyResultEnvelope], str]
StochasticEnvelopeRenderer = Callable[[StochasticResultEnvelope], str]


def _render_estimate_summary(envelope: EstimatorResultEnvelope) -> str:
    result = envelope.result
    if result is None:
        error_diag = next(
            (d for d in envelope.diagnostics if d.level == "error"),
            None,
        )
        if error_diag is not None:
            code = str(error_diag.code)
            input_name = error_diag.context.get("input_name")
            stage = error_diag.context.get("stage")
            if input_name and stage:
                return f"ERROR   [{code}: {input_name} {stage}]"
            return f"ERROR   [{code}]"
        return "ERROR"
    return format_estimate_summary(result)


def _scenario_result_from_envelope(envelope: ScenarioResultEnvelope) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=envelope.scenario_id,
        status=envelope.status,
        deterministic=envelope.determinism_metadata.deterministic,
        timeline=envelope.timeline,
        event_outcomes=envelope.event_outcomes,
        assertion_results=envelope.assertion_results,
        estimate=envelope.estimate,
    )


def _render_scenario_summary(envelope: ScenarioResultEnvelope) -> str:
    return format_scenario_summary(_scenario_result_from_envelope(envelope))


_ESTIMATE_RENDERERS: dict[OutputFormat, EstimatorEnvelopeRenderer] = {
    OutputFormat.JSON: render_envelope_json,
    OutputFormat.MARKDOWN: render_envelope_markdown,
    OutputFormat.SUMMARY: _render_estimate_summary,
    OutputFormat.CHECKLIST: render_checklist_markdown,
    OutputFormat.GROUND_RISK: render_ground_risk_markdown,
}

_SCENARIO_RENDERERS: dict[OutputFormat, ScenarioEnvelopeRenderer] = {
    OutputFormat.JSON: render_scenario_envelope_json,
    OutputFormat.MARKDOWN: render_scenario_markdown,
    OutputFormat.SUMMARY: _render_scenario_summary,
    OutputFormat.CHECKLIST: render_checklist_markdown_from_scenario,
    OutputFormat.GROUND_RISK: render_ground_risk_markdown_from_scenario,
}


def _render_uncertainty_summary(envelope: UncertaintyResultEnvelope) -> str:
    return format_uncertainty_summary(envelope.result)


_UNCERTAINTY_RENDERERS: dict[OutputFormat, UncertaintyEnvelopeRenderer] = {
    OutputFormat.JSON: render_uncertainty_envelope_json,
    OutputFormat.MARKDOWN: render_uncertainty_markdown,
    OutputFormat.SUMMARY: _render_uncertainty_summary,
}


def _render_stochastic_summary(envelope: StochasticResultEnvelope) -> str:
    return format_stochastic_summary(envelope.result)


_STOCHASTIC_RENDERERS: dict[OutputFormat, StochasticEnvelopeRenderer] = {
    OutputFormat.JSON: render_stochastic_envelope_json,
    OutputFormat.MARKDOWN: render_stochastic_markdown,
    OutputFormat.SUMMARY: _render_stochastic_summary,
}


def _render_output(
    output_format: OutputFormat,
    envelope: EstimatorResultEnvelope,
    *,
    mission_id: str | None = None,
) -> str:
    if output_format == OutputFormat.CHECKLIST and mission_id is not None:
        return render_checklist_markdown(envelope, mission_id=mission_id)
    return _ESTIMATE_RENDERERS[output_format](envelope)


def _render_scenario_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
) -> str:
    return _SCENARIO_RENDERERS[output_format](envelope)


def _render_uncertainty_output(
    output_format: OutputFormat,
    envelope: UncertaintyResultEnvelope,
) -> str:
    return _UNCERTAINTY_RENDERERS[output_format](envelope)


def _render_stochastic_output(
    output_format: OutputFormat,
    envelope: StochasticResultEnvelope,
) -> str:
    return _STOCHASTIC_RENDERERS[output_format](envelope)


def _load_optional_asset(
    path: Path | None,
    *,
    mission_path: Path,
    loader: Callable[[Path], tuple[LoadedAssetT, InputDocument]],
    cache: dict[Path, tuple[Any, InputDocument]] | None = None,
) -> tuple[LoadedAssetT | None, InputDocument | None]:
    if path is None:
        return None, None
    resolved = _resolve_asset_path(path, mission_path=mission_path)
    if cache is None:
        return loader(resolved)
    key = resolved.resolve(strict=False)
    if key not in cache:
        cache[key] = loader(resolved)
    value, document = cache[key]
    # Zone lists are handed to the estimator per run; copy so one run can
    # never see another's list object.
    if isinstance(value, list):
        value = list(value)
    return value, document


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
    if not all(isfinite(value) for value in (altitude_m, east, north)):
        raise InputLoadError(
            f"{_WIND_LAYER_FLAG} entry {i}: all three values must be finite.",
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
    if (fidelity, max_segment_length_m) == (None, None):
        return None
    try:
        return EstimationOptions(
            fidelity=fidelity,
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


def _populate_mission_assets(
    bundle: MissionAssetBundle,
    *,
    mission_model: MissionPlan,
    mission_document: InputDocument,
    asset_cache: dict[Path, tuple[Any, InputDocument]] | None = None,
) -> None:
    mission_path = mission_document.path
    bundle.terrain_provider, bundle.terrain_document = _load_optional_asset(
        mission_model.assets.terrain_file,
        mission_path=mission_path,
        loader=load_terrain_grid,
        cache=asset_cache,
    )
    bundle.population_provider, bundle.population_document = _load_optional_asset(
        mission_model.assets.population_grid_file,
        mission_path=mission_path,
        loader=load_population_grid,
        cache=asset_cache,
    )
    bundle.obstacle_provider, bundle.obstacle_document = _load_optional_asset(
        mission_model.assets.obstacles_file,
        mission_path=mission_path,
        loader=load_obstacles,
        cache=asset_cache,
    )
    bundle.wind_provider, bundle.wind_grid_document = _load_optional_asset(
        mission_model.assets.wind_grid_file,
        mission_path=mission_path,
        loader=load_wind_grid,
        cache=asset_cache,
    )
    bundle.geofences, bundle.geofence_document = _load_optional_asset(
        mission_model.assets.geofences_file,
        mission_path=mission_path,
        loader=load_geofences,
        cache=asset_cache,
    )
    bundle.landing_zones, bundle.landing_zone_document = _load_optional_asset(
        mission_model.assets.landing_zones_file,
        mission_path=mission_path,
        loader=load_landing_zones,
        cache=asset_cache,
    )


def _envelope_inputs_for_static_asset_error(
    error: GeoJsonAssetLoadError,
    *,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
    mission_assets: MissionAssetBundle,
) -> EnvelopeInputs | None:
    if None in (mission_document, vehicle_document):
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
        population=mission_assets.population_document,
        obstacles=(
            error.document
            if isinstance(error, ObstacleLoadError)
            else mission_assets.obstacle_document
        ),
        wind_grid=mission_assets.wind_grid_document,
    )


def _input_error_for_geojson_asset_error(
    error: GeoJsonAssetLoadError,
) -> InputLoadError:
    input_name = _geojson_asset_input_name(error)
    return InputLoadError(
        str(error),
        input_name=input_name,
        path=error.path,
        stage=InputLoadStage.SCHEMA_VALIDATION,
        details=error.failure.context,
        document=error.document,
    )


def _geojson_asset_input_name(error: GeoJsonAssetLoadError) -> str:
    if isinstance(error, GeofenceLoadError):
        return "geofences"
    if isinstance(error, LandingZoneLoadError):
        return "landing_zones"
    return "obstacles"


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
        population_provider=mission_assets.population_provider,
        obstacle_provider=mission_assets.obstacle_provider,
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
        population_document=mission_assets.population_document,
        obstacle_document=mission_assets.obstacle_document,
        wind_grid_document=mission_assets.wind_grid_document,
    )


def _resolve_generated_at(raw: str) -> str:
    """Resolve a --generated-at value to an ISO 8601 UTC timestamp string."""
    if raw == "now":
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        datetime.fromisoformat(raw)
    except ValueError:
        raise InputLoadError(
            f"{_GENERATED_AT_FLAG} must be an ISO 8601 timestamp or 'now'.",
            input_name=_GENERATED_AT_FLAG,
            path=Path(_GENERATED_AT_FLAG),
            stage=InputLoadStage.PARSE,
            details={"raw": raw},
        ) from None
    return raw


def _provenance_metadata(
    operator_id: str | None,
    generated_at: str | None,
) -> dict[str, str]:
    """Metadata entries for --operator-id/--generated-at; empty when absent.

    An empty map means the flags were not given and the result envelope must
    stay byte-identical to a run without them.
    """
    entries: dict[str, str] = {}
    if operator_id is not None:
        entries["operator_id"] = operator_id
    if generated_at is not None:
        entries["generated_at"] = _resolve_generated_at(generated_at)
    return entries


def _refuse_output_clobber(
    output: Path | None,
    *,
    no_clobber: bool,
    command: str,
) -> None:
    """Exit INVALID_INPUT when --no-clobber is set and the output file exists."""
    if not no_clobber or output is None or not output.exists():
        return
    import adapters.cli as cli

    cli._exit_with_cli_error(
        f"--no-clobber: refusing to overwrite existing output file: {output}",
        command=command,
        code=cli.CliExitCode.INVALID_INPUT,
    )


class OutputWriteError(OSError):
    """Raised when the CLI cannot write rendered output."""


_ROUTE_EXPORT_FORMATS: frozenset[OutputFormat] = frozenset(
    [OutputFormat.GEOJSON, OutputFormat.KML]
)


def _write_output(rendered: str, output: Path | None) -> None:
    try:
        if output is None:
            typer.echo(rendered, nl=not rendered.endswith("\n"))
            return
        atomic_write_text(output, rendered)
    except BrokenPipeError:
        # The downstream reader (head, less, ...) closed the pipe; close
        # stdout quietly so interpreter shutdown does not report the failure.
        with contextlib.suppress(OSError):
            sys.stdout.close()
        raise typer.Exit(code=0) from None
    except AtomicWriteDurabilityError as exc:
        raise OutputWriteError(
            "Output was replaced, but filesystem durability could not be confirmed."
        ) from exc
    except OSError as exc:
        raise OutputWriteError("Failed to write output.") from exc


def _envelope_output_format(output_format: OutputFormat) -> OutputFormat:
    if output_format in _ROUTE_EXPORT_FORMATS:
        return OutputFormat.JSON
    return output_format


__all__ = [
    "GENERATED_AT_OPTION",
    "GeoJsonAssetLoadError",
    "LoadedAssetT",
    "MissionAssetBundle",
    "NO_CLOBBER_OPTION",
    "OPERATOR_ID_OPTION",
    "SitlScenarioContext",
    "_build_estimation_options",
    "_build_scenario_result_envelope",
    "_empty_failed_result",
    "_envelope_inputs_for_static_asset_error",
    "_input_error_for_geojson_asset_error",
    "_load_optional_asset",
    "_parse_wind_layer_entry",
    "_parse_wind_layers",
    "_populate_mission_assets",
    "_envelope_output_format",
    "_provenance_metadata",
    "_refuse_output_clobber",
    "_render_output",
    "_render_scenario_output",
    "_render_stochastic_output",
    "_render_uncertainty_output",
    "_resolve_asset_path",
    "_resolve_generated_at",
    "_resolve_scenario_input_paths",
    "_run_scenario_with_assets",
    "_write_output",
    "OutputWriteError",
]
