"""Minimum battery capacity sizing for mission estimates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from estimator import (
    EstimateStatus,
    GeofenceZone,
    LandingZone,
    TerrainProvider,
    WindProvider,
    try_estimate_mission_distance_time,
)
from estimator.core.results import EnergyEstimate, MissionEstimate
from schemas import MissionPlan, VehicleProfile

_DEFAULT_SAFETY_MARGINS = [10, 20, 30]
_MAX_UPPER_BOUND_EXPANSIONS = 40


@dataclass(frozen=True)
class BatterySizingResult:
    mission_energy_wh: float
    reserve_threshold_wh: float
    minimum_capacity_wh: float
    current_capacity_wh: float
    current_reserve_wh: float
    current_reserve_pct: float
    is_current_feasible: bool


def compute_minimum_battery_capacity(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    tolerance_wh: float = 1.0,
    max_iterations: int = 40,
) -> BatterySizingResult:
    """Binary-search battery capacity until reserve just meets threshold."""
    if tolerance_wh <= 0.0:
        raise ValueError("tolerance_wh must be greater than zero.")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than zero.")

    current_capacity_wh = vehicle.energy.battery_capacity_wh
    current_estimate = _estimate_at_capacity(
        mission,
        vehicle,
        current_capacity_wh,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    current_energy = _require_energy(current_estimate)
    mission_energy_wh = current_energy.total_energy_wh
    current_feasible = _is_estimate_feasible(current_estimate)

    lower = 0.0
    upper = _initial_upper_bound(
        current_capacity_wh=current_capacity_wh,
        mission_energy_wh=mission_energy_wh,
        current_feasible=current_feasible,
    )
    upper = _find_feasible_upper_bound(
        mission,
        vehicle,
        upper,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )

    for _ in range(max_iterations):
        if upper - lower < tolerance_wh:
            break
        candidate = (lower + upper) * 0.5
        candidate_estimate = _estimate_at_capacity(
            mission,
            vehicle,
            candidate,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
        if _is_estimate_feasible(candidate_estimate):
            upper = candidate
        else:
            lower = candidate

    return BatterySizingResult(
        mission_energy_wh=mission_energy_wh,
        reserve_threshold_wh=current_energy.reserve_threshold_wh,
        minimum_capacity_wh=upper,
        current_capacity_wh=current_capacity_wh,
        current_reserve_wh=current_energy.reserve_at_landing_wh,
        current_reserve_pct=current_energy.reserve_at_landing_percent,
        is_current_feasible=current_feasible,
    )


def render_battery_sizing_markdown(
    result: BatterySizingResult,
    *,
    mission_id: str,
    safety_margins: list[int] | None = None,
) -> str:
    """Render the sizing result as Markdown."""
    margins = _safety_margins(safety_margins)
    lines = [f"## Battery Sizing: {mission_id}", ""]
    if result.is_current_feasible:
        minimum_margin_wh = result.current_capacity_wh - result.minimum_capacity_wh
        minimum_margin_pct = _percent_over_minimum(result)
        lines.extend(
            [
                f"Current capacity:   {_wh(result.current_capacity_wh)}",
                (
                    "Reserve at landing: "
                    f"{_wh(result.current_reserve_wh)} "
                    f"({_pct(result.current_reserve_pct)} of capacity)"
                ),
                f"Minimum feasible:   {_wh(result.minimum_capacity_wh)}",
                (
                    "Margin over minimum: "
                    f"{_wh(minimum_margin_wh)} "
                    f"({_pct(minimum_margin_pct)} above minimum)"
                ),
                "",
                (
                    "Status: FEASIBLE (current battery exceeds minimum by "
                    f"{minimum_margin_pct:.1f}%)"
                ),
            ]
        )
        return "\n".join(lines) + "\n"

    threshold_pct = _reserve_threshold_pct(result)
    lines.extend(
        [
            f"Mission energy required:   {_wh(result.mission_energy_wh)}",
            (
                f"Reserve threshold ({threshold_pct:.0f} %):  "
                f"{_wh(result.reserve_threshold_wh)} (of battery capacity)"
            ),
            "",
            f"Minimum feasible capacity: {_wh(result.minimum_capacity_wh)}",
        ]
    )
    for margin in margins:
        label = f"With {margin} % safety margin:"
        lines.append(f"{label:<29} {_wh(_capacity_with_margin(result, margin))}")
    lines.append("")
    if margins:
        recommendation_margin = margins[0]
        recommendation_wh = _capacity_with_margin(result, recommendation_margin)
        lines.append(
            "Recommendation: use >= "
            f"{recommendation_wh:.1f} Wh battery "
            f"({recommendation_margin} % margin above minimum feasible)"
        )
        lines.append("")
    lines.append("Status: SIZED")
    return "\n".join(lines) + "\n"


def render_battery_sizing_summary(
    result: BatterySizingResult,
    *,
    safety_margins: list[int] | None = None,
) -> str:
    """Render the sizing result as a single-line summary."""
    margins = _safety_margins(safety_margins)
    recommendation_margin = margins[0] if margins else 0
    recommendation_wh = _capacity_with_margin(result, recommendation_margin)
    status = "FEASIBLE" if result.is_current_feasible else "SIZED"
    return (
        f"{status}   minimum {result.minimum_capacity_wh:.1f} Wh"
        f"   current {result.current_capacity_wh:.1f} Wh"
        f"   recommendation {recommendation_wh:.1f} Wh"
    )


def _estimate_at_capacity(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    battery_capacity_wh: float,
    *,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> MissionEstimate:
    sized_vehicle = _vehicle_with_capacity(vehicle, battery_capacity_wh)
    return try_estimate_mission_distance_time(
        mission,
        sized_vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=list(geofences) if geofences is not None else None,
        landing_zones=list(landing_zones) if landing_zones is not None else None,
    )


def _vehicle_with_capacity(
    vehicle: VehicleProfile,
    battery_capacity_wh: float,
) -> VehicleProfile:
    energy = vehicle.energy
    return vehicle.model_copy(
        update={
            "energy": energy.model_copy(
                update={"battery_capacity_wh": battery_capacity_wh}
            )
        }
    )


def _require_energy(estimate: MissionEstimate) -> EnergyEstimate:
    if estimate.energy is None:
        raise ValueError("Mission estimate did not produce an energy result.")
    return estimate.energy


def _is_estimate_feasible(estimate: MissionEstimate) -> bool:
    return (
        estimate.status == EstimateStatus.SUCCESS
        and estimate.energy is not None
        and estimate.energy.is_feasible
    )


def _initial_upper_bound(
    *,
    current_capacity_wh: float,
    mission_energy_wh: float,
    current_feasible: bool,
) -> float:
    if current_feasible:
        return max(current_capacity_wh * 2.0, 1.0)
    return max(current_capacity_wh * 2.0, mission_energy_wh * 4.0, 1.0)


def _find_feasible_upper_bound(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    upper: float,
    *,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> float:
    for _ in range(_MAX_UPPER_BOUND_EXPANSIONS):
        estimate = _estimate_at_capacity(
            mission,
            vehicle,
            upper,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
        if _is_estimate_feasible(estimate):
            return upper
        upper *= 2.0
    raise ValueError("No feasible battery capacity found within search bounds.")


def _safety_margins(safety_margins: list[int] | None) -> list[int]:
    if safety_margins is None:
        return list(_DEFAULT_SAFETY_MARGINS)
    if any(margin < 0 for margin in safety_margins):
        raise ValueError("Safety margins must be non-negative percentages.")
    return list(safety_margins)


def _capacity_with_margin(result: BatterySizingResult, margin_percent: int) -> float:
    return result.minimum_capacity_wh * (1.0 + margin_percent / 100.0)


def _percent_over_minimum(result: BatterySizingResult) -> float:
    if result.minimum_capacity_wh <= 0.0:
        return 0.0
    return (
        (result.current_capacity_wh - result.minimum_capacity_wh)
        / result.minimum_capacity_wh
        * 100.0
    )


def _reserve_threshold_pct(result: BatterySizingResult) -> float:
    if result.current_capacity_wh <= 0.0:
        return 0.0
    return result.reserve_threshold_wh / result.current_capacity_wh * 100.0


def _wh(value: float) -> str:
    return f"{value:.1f} Wh"


def _pct(value: float) -> str:
    return f"{value:.1f}%"
