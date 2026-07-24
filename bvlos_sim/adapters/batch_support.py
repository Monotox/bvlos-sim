"""Batch estimate execution support for CLI and tests."""

from collections.abc import Callable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from bvlos_sim.adapters.checklist_markdown import checklist_is_go
from bvlos_sim.adapters.cli_support import (
    MissionAssetBundle,
    _build_scenario_result_envelope,
    _populate_mission_assets,
    _resolve_scenario_input_paths,
    _run_scenario_with_assets,
)
from bvlos_sim.adapters.envelope import EstimatorResultEnvelope, build_estimator_envelope
from bvlos_sim.adapters.assets.geofence_geojson import GeofenceLoadError
from bvlos_sim.adapters.assets.obstacle_geojson import ObstacleLoadError
from bvlos_sim.adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from bvlos_sim.adapters.assets.landing_zone_geojson import LandingZoneLoadError
from bvlos_sim.adapters.assets.terrain_grid import TerrainGridLoadError
from bvlos_sim.adapters.assets.wind_grid import WindGridLoadError
from bvlos_sim.adapters.scenario_envelope import (
    ScenarioResultEnvelope,
    scenario_readiness,
)
from bvlos_sim.adapters.scenario_io import load_scenario
from bvlos_sim.adapters.stochastic_envelope import (
    StochasticResultEnvelope,
    build_stochastic_envelope,
)
from bvlos_sim.adapters.stochastic_io import load_stochastic_plan, resolve_stochastic_asset_path
from bvlos_sim.estimator import (
    EstimateStatus,
    GeofenceZone,
    LandingZone,
    MissionEstimate,
    Obstacle,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.enums import AssertionOutcome, ScenarioStatus
from bvlos_sim.estimator.core.scenario import ScenarioResult
from bvlos_sim.estimator.environment.terrain import TerrainProvider
from bvlos_sim.estimator.execution.propagator import run_stochastic_propagation
from bvlos_sim.schemas.batch import BatchManifest, BatchRun, RunType
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.vehicle import VehicleProfile


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
    run_type: RunType = "estimate"
    scenario_envelope: ScenarioResultEnvelope | None = None
    stochastic_envelope: StochasticResultEnvelope | None = None
    assertions_passed: int | None = None
    assertions_total: int | None = None
    modeled_pass_rate: float | None = None
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


def _load_run_mission_vehicle(
    mission_path: Path,
    vehicle_path: Path,
    caches: _BatchLoadCaches,
) -> tuple[MissionPlan, InputDocument, VehicleProfile, InputDocument, MissionAssetBundle]:
    mission_key = mission_path.resolve(strict=False)
    if mission_key not in caches.missions:
        caches.missions[mission_key] = load_mission(mission_path)
    mission_model, mission_document = caches.missions[mission_key]
    vehicle_key = vehicle_path.resolve(strict=False)
    if vehicle_key not in caches.vehicles:
        caches.vehicles[vehicle_key] = load_vehicle(vehicle_path)
    vehicle_model, vehicle_document = caches.vehicles[vehicle_key]
    mission_assets = MissionAssetBundle()
    _populate_mission_assets(
        mission_assets,
        mission_model=mission_model,
        mission_document=mission_document,
        asset_cache=caches.assets,
    )
    return mission_model, mission_document, vehicle_model, vehicle_document, mission_assets


def _run_scenario(
    run: BatchRun,
    *,
    caches: _BatchLoadCaches,
    engineering_only: bool = False,
) -> BatchRunResult:
    assert run.scenario is not None
    scenario_plan, scenario_document = load_scenario(run.scenario)
    mission_path, vehicle_path = _resolve_scenario_input_paths(
        scenario_plan, scenario_file=run.scenario
    )
    mission_model, mission_document, vehicle_model, vehicle_document, mission_assets = (
        _load_run_mission_vehicle(mission_path, vehicle_path, caches)
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
    passed = sum(
        assertion.outcome == AssertionOutcome.PASSED
        for assertion in result.assertion_results
    )
    warnings = result.estimate.warnings if result.estimate is not None else []
    return BatchRunResult(
        id=run.id,
        status=_scenario_status_label(result, engineering_only=engineering_only),
        run_type="scenario",
        reserve_margin_percent=None,
        flight_time_s=result.estimate.total_time_s
        if result.estimate is not None
        else None,
        envelope=None,
        scenario_envelope=envelope,
        assertions_passed=passed,
        assertions_total=len(result.assertion_results),
        warning_count=len(warnings),
    )


def _batch_run_error(run: BatchRun, run_type: RunType, message: str) -> BatchRunResult:
    """Name the run and the file that failed, not just the error."""

    source = run.mission or run.scenario or run.plan
    where = f"{run.id} ({source})" if source is not None else run.id
    return BatchRunResult(
        id=run.id,
        status="ERROR",
        run_type=run_type,
        reserve_margin_percent=None,
        flight_time_s=None,
        envelope=None,
        error_message=f"{where}: {message}",
    )


def _scenario_status_label(
    result: ScenarioResult,
    *,
    engineering_only: bool = False,
) -> str:
    if result.status == ScenarioStatus.PASSED:
        # Mirror the scenario command: passing assertions alone is not a GO.
        # Without this a batch grades only whether an assertion actively
        # failed, so a mission the estimator calls INFEASIBLE still reads
        # PASSED and the batch exits 0.
        if not engineering_only and not scenario_readiness(result).is_go:
            return "FAILED"
        return "PASSED"
    if result.status == ScenarioStatus.FAILED:
        return "FAILED"
    return "ERROR"


def _run_propagate(
    run: BatchRun,
    *,
    caches: _BatchLoadCaches,
    engineering_only: bool = False,
) -> BatchRunResult:
    del engineering_only  # propagation has no operational GO gate
    assert run.plan is not None
    plan, stochastic_document = load_stochastic_plan(run.plan)
    mission_path = resolve_stochastic_asset_path(
        plan.mission_file, stochastic_path=run.plan
    )
    vehicle_path = resolve_stochastic_asset_path(
        plan.vehicle_file, stochastic_path=run.plan
    )
    mission_model, mission_document, vehicle_model, vehicle_document, mission_assets = (
        _load_run_mission_vehicle(mission_path, vehicle_path, caches)
    )
    result = run_stochastic_propagation(
        plan,
        mission_model,
        vehicle_model,
        wind_provider=mission_assets.wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        population_provider=mission_assets.population_provider,
        obstacle_provider=mission_assets.obstacle_provider,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )
    envelope = build_stochastic_envelope(
        result=result,
        stochastic_document=stochastic_document,
        mission_document=mission_document,
        vehicle_document=vehicle_document,
    )
    return BatchRunResult(
        id=run.id,
        status="DIAGNOSTIC",
        run_type="propagate",
        reserve_margin_percent=None,
        flight_time_s=None,
        envelope=None,
        stochastic_envelope=envelope,
        modeled_pass_rate=result.modeled_constraint_pass_rate,
    )


_RUN_DISPATCH: dict[RunType, Callable[..., BatchRunResult]] = {
    "estimate": _run_estimate,
    "scenario": _run_scenario,
    "propagate": _run_propagate,
}


def run_batch_manifest(
    manifest: BatchManifest,
    *,
    progress: Callable[[int, int, str], None] | None = None,
    engineering_only: bool = False,
    preloaded_missions: dict[Path, tuple[MissionPlan, InputDocument]] | None = None,
) -> list[BatchRunResult]:
    """Run every job in a validated batch manifest, dispatched by run_type."""
    results: list[BatchRunResult] = []
    total = len(manifest.runs)
    caches = _BatchLoadCaches(missions=dict(preloaded_missions or {}))
    for index, run in enumerate(manifest.runs):
        try:
            if manifest.run_type == "estimate":
                results.append(
                    _run_estimate(
                        run, engineering_only=engineering_only, caches=caches
                    )
                )
            else:
                results.append(
                    _RUN_DISPATCH[manifest.run_type](
                        run, caches=caches, engineering_only=engineering_only
                    )
                )
        except _BATCH_RUN_INPUT_ERRORS as exc:
            results.append(_batch_run_error(run, manifest.run_type, str(exc)))
        except Exception as exc:  # noqa: BLE001
            # One bad run must not discard every run that already completed.
            results.append(
                _batch_run_error(
                    run, manifest.run_type, f"{type(exc).__name__}: {exc}"
                )
            )
        if progress is not None:
            progress(index + 1, total, run.id)
    return results


# Statuses that stop the run (map to exit 10), success statuses, and errors.
_STOP_STATUSES = frozenset({"INFEASIBLE", "FAILED"})
_ERROR_STATUSES = frozenset({"ERROR"})


def summarize_batch(results: list[BatchRunResult]) -> BatchSummary:
    """Summarize batch run statuses into success / stop / error buckets.

    ``feasible_count`` is the success bucket (FEASIBLE, PASSED, DIAGNOSTIC),
    ``infeasible_count`` is the stop bucket (INFEASIBLE, FAILED) that drives
    exit 10, and ``error_count`` is load/run errors (exit 11).
    """
    error_count = sum(result.status in _ERROR_STATUSES for result in results)
    stop_count = sum(result.status in _STOP_STATUSES for result in results)
    success_count = len(results) - error_count - stop_count
    return BatchSummary(
        feasible_count=success_count,
        infeasible_count=stop_count,
        error_count=error_count,
    )


def _common_run_type(results: list[BatchRunResult]) -> RunType:
    return results[0].run_type if results else "estimate"


def format_assertions(passed: int | None, total: int | None) -> str:
    if passed is None or total is None:
        return "—"
    return f"{passed}/{total}"


def format_pass_rate(modeled_pass_rate: float | None) -> str:
    if modeled_pass_rate is None:
        return "—"
    return f"{modeled_pass_rate * 100:.0f} %"


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
    """Render the batch result table as CSV, with columns per run type."""
    run_type = _common_run_type(results)
    if run_type == "scenario":
        rows = ["id,status,assertions_passed,assertions_total,warning_count"]
        for r in results:
            passed = "" if r.assertions_passed is None else str(r.assertions_passed)
            total = "" if r.assertions_total is None else str(r.assertions_total)
            rows.append(f"{r.id},{r.status},{passed},{total},{r.warning_count}")
        return "\n".join(rows) + "\n"
    if run_type == "propagate":
        rows = ["id,status,modeled_pass_rate"]
        for r in results:
            rate = "" if r.modeled_pass_rate is None else f"{r.modeled_pass_rate:.4f}"
            rows.append(f"{r.id},{r.status},{rate}")
        return "\n".join(rows) + "\n"
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


def _summary_line(run_type: RunType, results: list[BatchRunResult]) -> str:
    summary = summarize_batch(results)
    if run_type == "scenario":
        return (
            f"{len(results)} runs: {summary.feasible_count} passed, "
            f"{summary.infeasible_count} failed, {summary.error_count} errors"
        )
    if run_type == "propagate":
        return (
            f"{len(results)} runs: {summary.feasible_count} completed, "
            f"{summary.error_count} errors"
        )
    return (
        f"{len(results)} runs: {summary.feasible_count} feasible, "
        f"{summary.infeasible_count} infeasible, {summary.error_count} errors"
    )


def render_batch_table(results: list[BatchRunResult]) -> str:
    """Render the batch result table with Rich, with columns per run type."""
    run_type = _common_run_type(results)
    table = Table(box=box.SIMPLE, show_edge=False)
    table.add_column("id")
    table.add_column("status")
    if run_type == "scenario":
        table.add_column("assertions")
        table.add_column("warnings")
        for result in results:
            table.add_row(
                result.id,
                result.status,
                format_assertions(result.assertions_passed, result.assertions_total),
                str(result.warning_count) if result.warning_count > 0 else "—",
            )
    elif run_type == "propagate":
        table.add_column("modeled pass rate")
        for result in results:
            table.add_row(
                result.id,
                result.status,
                format_pass_rate(result.modeled_pass_rate),
            )
    else:
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

    buffer = StringIO()
    console = Console(
        color_system=None,
        file=buffer,
        force_terminal=False,
        width=100,
    )
    console.print(table)
    console.print(_summary_line(run_type, results))
    return buffer.getvalue()
