"""Batch estimate execution support for CLI and tests."""

from collections.abc import Callable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from adapters.checklist_markdown import checklist_is_go
from adapters.cli_support import MissionAssetBundle, _populate_mission_assets
from adapters.envelope import EstimatorResultEnvelope, build_estimator_envelope
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.assets.terrain_grid import TerrainGridLoadError
from adapters.assets.wind_grid import WindGridLoadError
from estimator import (
    EstimateStatus,
    GeofenceZone,
    LandingZone,
    MissionEstimate,
    Obstacle,
    try_estimate_mission_distance_time,
)
from estimator.environment.terrain import TerrainProvider
from schemas.batch import BatchManifest, BatchRun
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile


@dataclass
class _BatchLoadCaches:
    """Per-invocation caches so shared inputs parse once across runs."""

    missions: dict[Path, tuple[MissionPlan, InputDocument]] = field(
        default_factory=dict
    )
    vehicles: dict[Path, tuple[VehicleProfile, InputDocument]] = field(
        default_factory=dict
    )
    assets: dict[Path, tuple[Any, InputDocument]] = field(default_factory=dict)

_BATCH_RUN_INPUT_ERRORS = (
    InputLoadError,
    GeofenceLoadError,
    LandingZoneLoadError,
    ObstacleLoadError,
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
    geofences: list[GeofenceZone] | None = None
    landing_zones: list[LandingZone] | None = None
    obstacles: tuple[Obstacle, ...] | None = None
    terrain_provider: TerrainProvider | None = None
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


def _status_label(
    estimate: MissionEstimate,
    *,
    engineering_only: bool,
) -> str:
    if (
        estimate.status == EstimateStatus.SUCCESS
        and not engineering_only
        and not checklist_is_go(estimate)
    ):
        return "INFEASIBLE"
    return _STATUS_LABELS.get(estimate.status, "ERROR")


def _run_estimate(
    run: BatchRun,
    *,
    engineering_only: bool,
    caches: _BatchLoadCaches | None = None,
) -> BatchRunResult:
    caches = caches or _BatchLoadCaches()
    mission_assets = MissionAssetBundle()
    mission_key = run.mission.resolve(strict=False)
    if mission_key not in caches.missions:
        caches.missions[mission_key] = load_mission(run.mission)
    mission_model, mission_document = caches.missions[mission_key]
    vehicle_key = run.vehicle.resolve(strict=False)
    if vehicle_key not in caches.vehicles:
        caches.vehicles[vehicle_key] = load_vehicle(run.vehicle)
    vehicle_model, vehicle_document = caches.vehicles[vehicle_key]
    _populate_mission_assets(
        mission_assets,
        mission_model=mission_model,
        mission_document=mission_document,
        asset_cache=caches.assets,
    )
    result = try_estimate_mission_distance_time(
        mission_model,
        vehicle_model,
        wind_provider=mission_assets.wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        population_provider=mission_assets.population_provider,
        obstacle_provider=mission_assets.obstacle_provider,
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
        status=_status_label(result, engineering_only=engineering_only),
        reserve_margin_percent=_reserve_margin_percent(result),
        flight_time_s=result.total_time_s,
        envelope=envelope,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
        obstacles=mission_assets.obstacle_provider.obstacles()
        if mission_assets.obstacle_provider is not None
        else None,
        terrain_provider=mission_assets.terrain_provider,
        warning_count=len(result.warnings),
    )


def run_batch_manifest(
    manifest: BatchManifest,
    *,
    progress: Callable[[int, int, str], None] | None = None,
    engineering_only: bool = False,
    preloaded_missions: dict[Path, tuple[MissionPlan, InputDocument]] | None = None,
) -> list[BatchRunResult]:
    """Run all estimates in a validated batch manifest."""
    results: list[BatchRunResult] = []
    total = len(manifest.runs)
    caches = _BatchLoadCaches(missions=dict(preloaded_missions or {}))
    for index, run in enumerate(manifest.runs):
        try:
            results.append(
                _run_estimate(run, engineering_only=engineering_only, caches=caches)
            )
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
        if progress is not None:
            progress(index + 1, total, run.id)
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


def render_batch_csv(results: list[BatchRunResult]) -> str:
    """Render the batch result table as CSV (suitable for import into spreadsheets)."""
    rows = ["id,status,reserve_margin_percent,flight_time_s,warning_count"]
    for r in results:
        reserve = (
            ""
            if r.reserve_margin_percent is None
            else f"{r.reserve_margin_percent:.2f}"
        )
        flight_time = "" if r.flight_time_s is None else f"{r.flight_time_s:.1f}"
        rows.append(f"{r.id},{r.status},{reserve},{flight_time},{r.warning_count}")
    return "\n".join(rows) + "\n"


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
