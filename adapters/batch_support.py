"""Batch estimate execution support for CLI and tests."""

from dataclasses import dataclass
from io import StringIO

from rich import box
from rich.console import Console
from rich.table import Table

from adapters.cli_support import MissionAssetBundle, _populate_mission_assets
from adapters.envelope import EstimatorResultEnvelope, build_estimator_envelope
from adapters.geofence_geojson import GeofenceLoadError
from adapters.io import InputLoadError, load_mission, load_vehicle
from adapters.landing_zone_geojson import LandingZoneLoadError
from adapters.terrain_grid import TerrainGridLoadError
from adapters.wind_grid import WindGridLoadError
from estimator import (
    EstimateStatus,
    MissionEstimate,
    try_estimate_mission_distance_time,
)
from schemas.batch import BatchManifest, BatchRun

_BATCH_RUN_INPUT_ERRORS = (
    InputLoadError,
    GeofenceLoadError,
    LandingZoneLoadError,
    TerrainGridLoadError,
    WindGridLoadError,
)

_MINUS_SIGN = "\u2212"
_STATUS_LABELS: dict[EstimateStatus, str] = {
    EstimateStatus.SUCCESS: "FEASIBLE",
    EstimateStatus.INFEASIBLE: "INFEASIBLE",
    EstimateStatus.ERROR: "ERROR",
}


@dataclass(frozen=True)
class BatchRunResult:
    id: str
    status: str
    reserve_margin_percent: float | None
    flight_time_s: float | None
    envelope: EstimatorResultEnvelope | None
    warning_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    feasible_count: int
    infeasible_count: int
    error_count: int


def _reserve_margin_percent(estimate: MissionEstimate) -> float | None:
    energy = estimate.energy
    if energy is None:
        return None
    if energy.reserve_threshold_wh == 0:
        return None
    return (energy.reserve_at_landing_wh / energy.reserve_threshold_wh - 1) * 100


def _status_label(estimate: MissionEstimate) -> str:
    return _STATUS_LABELS.get(estimate.status, "ERROR")


def _run_estimate(run: BatchRun) -> BatchRunResult:
    mission_assets = MissionAssetBundle()
    mission_model, mission_document = load_mission(run.mission)
    vehicle_model, vehicle_document = load_vehicle(run.vehicle)
    _populate_mission_assets(
        mission_assets,
        mission_model=mission_model,
        mission_document=mission_document,
    )
    result = try_estimate_mission_distance_time(
        mission_model,
        vehicle_model,
        wind_provider=mission_assets.wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )
    envelope = build_estimator_envelope(
        result=result,
        inputs=mission_assets.envelope_inputs(
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        ),
    )
    return BatchRunResult(
        id=run.id,
        status=_status_label(result),
        reserve_margin_percent=_reserve_margin_percent(result),
        flight_time_s=result.total_time_s,
        envelope=envelope,
        warning_count=len(result.warnings),
    )


def run_batch_manifest(manifest: BatchManifest) -> list[BatchRunResult]:
    """Run all estimates in a validated batch manifest."""
    results: list[BatchRunResult] = []
    for run in manifest.runs:
        try:
            results.append(_run_estimate(run))
        except _BATCH_RUN_INPUT_ERRORS as exc:
            results.append(
                BatchRunResult(
                    id=run.id,
                    status="ERROR",
                    reserve_margin_percent=None,
                    flight_time_s=None,
                    envelope=None,
                    error_message=str(exc),
                )
            )
    return results


def summarize_batch(results: list[BatchRunResult]) -> BatchSummary:
    """Summarize batch run statuses."""
    feasible_count = sum(result.status == "FEASIBLE" for result in results)
    infeasible_count = sum(result.status == "INFEASIBLE" for result in results)
    error_count = sum(result.status == "ERROR" for result in results)
    return BatchSummary(
        feasible_count=feasible_count,
        infeasible_count=infeasible_count,
        error_count=error_count,
    )


def format_reserve_margin(reserve_margin_percent: float | None) -> str:
    """Format a signed reserve margin for batch table output."""
    if reserve_margin_percent is None:
        return "\u2014"
    sign = _MINUS_SIGN if reserve_margin_percent < 0 else "+"
    return f"{sign}{abs(reserve_margin_percent):.1f} %"


def format_flight_time(flight_time_s: float | None) -> str:
    """Format flight time seconds as Xm Ys for batch table output."""
    if flight_time_s is None:
        return "\u2014"
    minutes = int(flight_time_s // 60)
    seconds = int(flight_time_s % 60)
    return f"{minutes}m {seconds:02d}s"


def render_batch_table(results: list[BatchRunResult]) -> str:
    """Render the batch result table with Rich."""
    table = Table(box=box.SIMPLE, show_edge=False)
    table.add_column("id")
    table.add_column("status")
    table.add_column("reserve")
    table.add_column("flight time")
    table.add_column("warnings")
    for result in results:
        table.add_row(
            result.id,
            result.status,
            format_reserve_margin(result.reserve_margin_percent),
            format_flight_time(result.flight_time_s),
            str(result.warning_count) if result.warning_count > 0 else "—",
        )

    summary = summarize_batch(results)
    buffer = StringIO()
    console = Console(
        color_system=None,
        file=buffer,
        force_terminal=False,
        width=100,
    )
    console.print(table)
    console.print(
        f"{len(results)} runs: {summary.feasible_count} feasible, "
        f"{summary.infeasible_count} infeasible, {summary.error_count} errors"
    )
    return buffer.getvalue()
