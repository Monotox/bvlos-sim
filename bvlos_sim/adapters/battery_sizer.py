"""Minimum battery capacity sizing for mission estimates."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bvlos_sim.estimator import (
    EstimateStatus,
    FailureCode,
    GeofenceZone,
    GridPopulationProvider,
    LandingZone,
    ObstacleProvider,
    TerrainProvider,
    WindProvider,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.results import EnergyEstimate, MissionEstimate
from bvlos_sim.schemas import MissionPlan, VehicleProfile

_DEFAULT_SAFETY_MARGINS = [10, 20, 30]
_MINIMUM_POSITIVE_CAPACITY_WH = 1e-9
_MAX_SEARCH_PROBES = 1_000_000
_CAPACITY_DEPENDENT_FAILURE_CODES = frozenset(
    {
        FailureCode.INSUFFICIENT_ENERGY,
        FailureCode.RESERVE_BELOW_THRESHOLD,
        FailureCode.RTH_RESERVE_BELOW_THRESHOLD,
        FailureCode.LANDING_ZONE_REACHABLE_BUT_BELOW_RESERVE,
    }
)


@dataclass(frozen=True)
class BatterySizingResult:
    mission_energy_wh: float
    reserve_threshold_wh: float
    minimum_capacity_wh: float
    maximum_feasible_capacity_wh: float
    maximum_capacity_at_mtow_wh: float
    search_tolerance_wh: float
    current_capacity_wh: float
    current_reserve_wh: float
    current_reserve_pct: float
    is_current_feasible: bool


@dataclass(frozen=True)
class BatteryCapacityRecommendation:
    margin_percent: int
    requested_capacity_wh: float
    recommended_capacity_wh: float | None
    unavailable_reason: str | None


def compute_minimum_battery_capacity(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    population_provider: GridPopulationProvider | None = None,
    obstacle_provider: ObstacleProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    tolerance_wh: float = 1.0,
    max_iterations: int = 40,
) -> BatterySizingResult:
    """Find the first feasible capacity under battery-mass feedback.

    Feasibility is not assumed to be monotone: induced power can grow faster
    than pack capacity as battery mass increases. The mass-valid interval is
    therefore searched from low to high at ``tolerance_wh`` resolution until
    the first feasible transition, then its contiguous upper transition is
    verified. As with any point-sampled search, a feasible island narrower than
    the requested tolerance is below the caller-selected search resolution.
    """
    if not math.isfinite(tolerance_wh) or tolerance_wh <= 0.0:
        raise ValueError("tolerance_wh must be finite and greater than zero.")
    if max_iterations <= 0:
        raise ValueError("max_iterations must be greater than zero.")

    _require_capacity_mass_model(vehicle)

    current_capacity_wh = vehicle.energy.battery_capacity_wh
    current_estimate = _estimate_at_capacity(
        mission,
        vehicle,
        current_capacity_wh,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    current_feasible = _capacity_is_feasible_or_raise(current_estimate)
    current_energy = _require_energy(current_estimate)

    lower = _minimum_capacity_for_mass(vehicle)
    maximum_capacity_wh = _maximum_capacity_at_mtow(vehicle)
    minimum_capacity_wh, maximum_feasible_capacity_wh = _find_first_feasible_interval(
        mission,
        vehicle,
        lower=lower,
        upper=maximum_capacity_wh,
        tolerance_wh=tolerance_wh,
        max_iterations=max_iterations,
        current_capacity_wh=current_capacity_wh,
        current_estimate=current_estimate,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    minimum_estimate = (
        current_estimate
        if minimum_capacity_wh == current_capacity_wh
        else _estimate_at_capacity(
            mission,
            vehicle,
            minimum_capacity_wh,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            population_provider=population_provider,
            obstacle_provider=obstacle_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
    )
    if not _capacity_is_feasible_or_raise(minimum_estimate):
        raise ValueError("Refined minimum battery capacity is not feasible.")
    minimum_energy = _require_energy(minimum_estimate)

    return BatterySizingResult(
        mission_energy_wh=minimum_energy.total_energy_wh,
        reserve_threshold_wh=minimum_energy.reserve_threshold_wh,
        minimum_capacity_wh=minimum_capacity_wh,
        maximum_feasible_capacity_wh=maximum_feasible_capacity_wh,
        maximum_capacity_at_mtow_wh=maximum_capacity_wh,
        search_tolerance_wh=tolerance_wh,
        current_capacity_wh=current_capacity_wh,
        current_reserve_wh=current_energy.reserve_at_landing_wh,
        current_reserve_pct=current_energy.reserve_at_landing_percent,
        is_current_feasible=current_feasible,
    )


def battery_capacity_recommendations(
    result: BatterySizingResult,
    *,
    safety_margins: list[int] | None = None,
) -> list[BatteryCapacityRecommendation]:
    """Build only recommendations inside the verified feasible interval."""
    margins = _safety_margins(safety_margins)
    recommendations: list[BatteryCapacityRecommendation] = []
    for margin in margins:
        requested_capacity_wh = _capacity_with_margin(result, margin)
        if requested_capacity_wh <= result.maximum_feasible_capacity_wh:
            recommendations.append(
                BatteryCapacityRecommendation(
                    margin_percent=margin,
                    requested_capacity_wh=requested_capacity_wh,
                    recommended_capacity_wh=requested_capacity_wh,
                    unavailable_reason=None,
                )
            )
            continue
        recommendations.append(
            BatteryCapacityRecommendation(
                margin_percent=margin,
                requested_capacity_wh=requested_capacity_wh,
                recommended_capacity_wh=None,
                unavailable_reason=(
                    f"Requested {requested_capacity_wh:.1f} Wh exceeds the "
                    "verified maximum feasible capacity "
                    f"({result.maximum_feasible_capacity_wh:.1f} Wh) under "
                    "battery-mass feedback."
                ),
            )
        )
    return recommendations


def render_battery_sizing_markdown(
    result: BatterySizingResult,
    *,
    mission_id: str,
    safety_margins: list[int] | None = None,
) -> str:
    """Render the sizing result as Markdown."""
    recommendations = battery_capacity_recommendations(
        result,
        safety_margins=safety_margins,
    )
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
                (f"Maximum feasible:   {_wh(result.maximum_feasible_capacity_wh)}"),
                (
                    "Margin over minimum: "
                    f"{_wh(minimum_margin_wh)} "
                    f"({_pct(minimum_margin_pct)} above minimum)"
                ),
            ]
        )
    else:
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
                (
                    "Maximum feasible capacity: "
                    f"{_wh(result.maximum_feasible_capacity_wh)}"
                ),
            ]
        )

    lines.extend(["", f"Search resolution: {_wh(result.search_tolerance_wh)}"])
    for recommendation in recommendations:
        label = f"With {recommendation.margin_percent} % safety margin:"
        if recommendation.recommended_capacity_wh is None:
            lines.append(
                f"{label:<29} UNAVAILABLE — {recommendation.unavailable_reason}"
            )
        else:
            lines.append(f"{label:<29} {_wh(recommendation.recommended_capacity_wh)}")

    available_recommendation = next(
        (
            recommendation
            for recommendation in recommendations
            if recommendation.recommended_capacity_wh is not None
        ),
        None,
    )
    lines.append("")
    if available_recommendation is not None:
        lines.append(
            "Recommendation: target "
            f"{available_recommendation.recommended_capacity_wh:.1f} Wh "
            f"({available_recommendation.margin_percent} % margin); do not exceed "
            f"the verified {result.maximum_feasible_capacity_wh:.1f} Wh upper bound."
        )
        lines.append("")
    elif recommendations:
        lines.extend(
            [
                (
                    "Recommendation: none of the requested safety margins fits "
                    "inside the verified feasible interval."
                ),
                "",
            ]
        )

    if result.is_current_feasible:
        lines.append(
            "Status: FEASIBLE (current battery exceeds minimum by "
            f"{_percent_over_minimum(result):.1f}%)"
        )
    else:
        lines.append("Status: SIZED")
    return "\n".join(lines) + "\n"


def render_battery_sizing_summary(
    result: BatterySizingResult,
    *,
    safety_margins: list[int] | None = None,
) -> str:
    """Render the sizing result as a single-line summary."""
    recommendations = battery_capacity_recommendations(
        result,
        safety_margins=safety_margins,
    )
    available_recommendation = next(
        (
            recommendation.recommended_capacity_wh
            for recommendation in recommendations
            if recommendation.recommended_capacity_wh is not None
        ),
        None,
    )
    status = "FEASIBLE" if result.is_current_feasible else "SIZED"
    summary = (
        f"{status}   minimum {result.minimum_capacity_wh:.1f} Wh"
        f"   maximum {result.maximum_feasible_capacity_wh:.1f} Wh"
        f"   current {result.current_capacity_wh:.1f} Wh"
    )
    if available_recommendation is None:
        return summary + "   recommendation unavailable"
    return summary + f"   recommendation {available_recommendation:.1f} Wh"


def _estimate_at_capacity(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    battery_capacity_wh: float,
    *,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    population_provider: GridPopulationProvider | None,
    obstacle_provider: ObstacleProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> MissionEstimate:
    sized_vehicle = _vehicle_with_capacity(vehicle, battery_capacity_wh)
    return try_estimate_mission_distance_time(
        mission,
        sized_vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=list(geofences) if geofences is not None else None,
        landing_zones=list(landing_zones) if landing_zones is not None else None,
    )


def _vehicle_with_capacity(
    vehicle: VehicleProfile,
    battery_capacity_wh: float,
) -> VehicleProfile:
    _require_capacity_mass_model(vehicle)
    energy = vehicle.energy
    battery_excluded_mass_kg = energy.battery_excluded_operating_mass_kg
    specific_energy = energy.battery_specific_energy_wh_per_kg
    if battery_excluded_mass_kg is None or specific_energy is None:
        raise ValueError("Battery sizing mass inputs are unavailable.")
    sized_operating_mass_kg = battery_excluded_mass_kg + (
        battery_capacity_wh / specific_energy
    )
    reference_mass_kg = energy.reference_mass_kg or (
        battery_excluded_mass_kg + energy.battery_capacity_wh / specific_energy
    )
    payload = vehicle.model_dump(mode="python")
    payload["energy"]["battery_capacity_wh"] = battery_capacity_wh
    payload["energy"]["reference_mass_kg"] = reference_mass_kg
    payload["mass"]["operating_mass_kg"] = sized_operating_mass_kg
    return VehicleProfile.model_validate(payload)


def _require_capacity_mass_model(vehicle: VehicleProfile) -> None:
    if vehicle.resource_systems:
        raise ValueError(
            "Battery sizing cannot vary vehicle.resource_systems; it only sizes "
            "the legacy vehicle.energy battery."
        )
    missing: list[str] = []
    if vehicle.energy.battery_specific_energy_wh_per_kg is None:
        missing.append("vehicle.energy.battery_specific_energy_wh_per_kg")
    if vehicle.energy.battery_excluded_operating_mass_kg is None:
        missing.append("vehicle.energy.battery_excluded_operating_mass_kg")
    if missing:
        raise ValueError(
            "Battery sizing requires capacity-mass feedback inputs: "
            + ", ".join(missing)
            + "."
        )
    battery_excluded_mass_kg = vehicle.energy.battery_excluded_operating_mass_kg
    specific_energy = vehicle.energy.battery_specific_energy_wh_per_kg
    if battery_excluded_mass_kg is None or specific_energy is None:
        raise ValueError("Battery sizing mass inputs are unavailable.")
    if battery_excluded_mass_kg < vehicle.mass.empty_kg:
        raise ValueError(
            "vehicle.energy.battery_excluded_operating_mass_kg must be greater "
            "than or equal to vehicle.mass.empty_kg."
        )
    current_operating_mass_kg = battery_excluded_mass_kg + (
        vehicle.energy.battery_capacity_wh / specific_energy
    )
    if current_operating_mass_kg > vehicle.mass.max_takeoff_kg:
        raise ValueError(
            "Current battery mass places the vehicle above max_takeoff_kg."
        )


def _minimum_capacity_for_mass(vehicle: VehicleProfile) -> float:
    battery_excluded_mass_kg = vehicle.energy.battery_excluded_operating_mass_kg
    specific_energy = vehicle.energy.battery_specific_energy_wh_per_kg
    if battery_excluded_mass_kg is None or specific_energy is None:
        raise ValueError("Battery sizing mass inputs are unavailable.")
    capacity_at_empty_mass = (
        vehicle.mass.empty_kg - battery_excluded_mass_kg
    ) * specific_energy
    return max(_MINIMUM_POSITIVE_CAPACITY_WH, capacity_at_empty_mass)


def _maximum_capacity_at_mtow(vehicle: VehicleProfile) -> float:
    battery_excluded_mass_kg = vehicle.energy.battery_excluded_operating_mass_kg
    specific_energy = vehicle.energy.battery_specific_energy_wh_per_kg
    if battery_excluded_mass_kg is None or specific_energy is None:
        raise ValueError("Battery sizing mass inputs are unavailable.")
    return (vehicle.mass.max_takeoff_kg - battery_excluded_mass_kg) * specific_energy


def _require_energy(estimate: MissionEstimate) -> EnergyEstimate:
    if estimate.energy is None:
        raise ValueError("Mission estimate did not produce an energy result.")
    return estimate.energy


def _capacity_is_feasible_or_raise(estimate: MissionEstimate) -> bool:
    """Classify capacity feasibility and reject unrelated blockers."""
    if estimate.status == EstimateStatus.SUCCESS:
        energy = _require_energy(estimate)
        if not energy.is_feasible:
            raise ValueError(
                "Mission estimator returned success with an infeasible energy result."
            )
        return True

    failure = estimate.failure
    if failure is None:
        raise ValueError(
            "Mission estimator returned a non-success status without failure details."
        )
    if failure.code not in _CAPACITY_DEPENDENT_FAILURE_CODES:
        raise ValueError(
            "Battery sizing cannot resolve non-energy or non-capacity blocker "
            f"{failure.code.value}: {failure.message}"
        )
    _require_energy(estimate)
    return False


def _find_first_feasible_interval(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    lower: float,
    upper: float,
    tolerance_wh: float,
    max_iterations: int,
    current_capacity_wh: float,
    current_estimate: MissionEstimate,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    population_provider: GridPopulationProvider | None,
    obstacle_provider: ObstacleProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> tuple[float, float]:
    """Find the first contiguous feasible interval without monotonicity."""
    if not all(math.isfinite(bound) for bound in (lower, upper)):
        raise ValueError("Battery sizing capacity bounds must be finite.")
    if upper < lower:
        raise ValueError(
            "No positive battery capacity fits within vehicle mass.max_takeoff_kg."
        )

    span = upper - lower
    interval_count = 0 if span == 0.0 else math.ceil(span / tolerance_wh)
    probe_count = interval_count + 1
    if probe_count > _MAX_SEARCH_PROBES:
        raise ValueError(
            "Battery sizing would require "
            f"{probe_count:,} capacity probes at tolerance_wh={tolerance_wh:g}; "
            "increase tolerance_wh."
        )

    def estimate_at(capacity_wh: float) -> MissionEstimate:
        if capacity_wh == current_capacity_wh:
            return current_estimate
        return _estimate_at_capacity(
            mission,
            vehicle,
            capacity_wh,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            population_provider=population_provider,
            obstacle_provider=obstacle_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )

    previous_capacity = lower
    previous_feasible = _capacity_is_feasible_or_raise(estimate_at(lower))
    minimum_feasible_capacity_wh = lower if previous_feasible else None
    # Supported capacity-dependent margins are linear available energy minus
    # positive mass-power terms. Their feasible set is one interval (possibly
    # bounded at both ends), so a feasible MTOW endpoint proves that the first
    # interval extends to the physical limit. We still cannot assume the whole
    # function is monotone: both endpoints can be infeasible around a middle
    # feasible window, which is why lower-bound discovery remains exhaustive.
    if (
        minimum_feasible_capacity_wh is not None
        and upper > lower
        and _capacity_is_feasible_or_raise(estimate_at(upper))
    ):
        return minimum_feasible_capacity_wh, upper

    for interval_index in range(1, interval_count + 1):
        candidate = (
            upper
            if interval_index == interval_count
            else lower + span * interval_index / interval_count
        )
        candidate_feasible = _capacity_is_feasible_or_raise(estimate_at(candidate))
        if minimum_feasible_capacity_wh is None and candidate_feasible:
            minimum_feasible_capacity_wh = _refine_first_feasible_sample(
                previous_capacity,
                candidate,
                estimate_at=estimate_at,
                max_iterations=max_iterations,
            )
            if candidate < upper and _capacity_is_feasible_or_raise(estimate_at(upper)):
                return minimum_feasible_capacity_wh, upper
        elif minimum_feasible_capacity_wh is not None and not candidate_feasible:
            if not previous_feasible:
                raise ValueError(
                    "Battery sizing interval tracking lost its feasible upper bound."
                )
            maximum_feasible_capacity_wh = _refine_last_feasible_sample(
                previous_capacity,
                candidate,
                estimate_at=estimate_at,
                max_iterations=max_iterations,
            )
            return minimum_feasible_capacity_wh, maximum_feasible_capacity_wh
        previous_capacity = candidate
        previous_feasible = candidate_feasible

    if minimum_feasible_capacity_wh is not None:
        return minimum_feasible_capacity_wh, upper

    raise ValueError(
        "No feasible battery capacity found between the physical minimum and "
        "the vehicle's max_takeoff_kg limit "
        f"({vehicle.mass.max_takeoff_kg:.3f} kg) at "
        f"tolerance_wh={tolerance_wh:g}. Reduce tolerance_wh to search for a "
        "narrower feasible interval."
    )


def _refine_first_feasible_sample(
    infeasible_capacity_wh: float,
    feasible_capacity_wh: float,
    *,
    estimate_at: Callable[[float], MissionEstimate],
    max_iterations: int,
) -> float:
    """Refine inside one sampled interval while retaining a feasible bound."""
    lower = infeasible_capacity_wh
    upper = feasible_capacity_wh
    for _ in range(max_iterations):
        candidate = (lower + upper) * 0.5
        if candidate == lower or candidate == upper:
            break
        if _capacity_is_feasible_or_raise(estimate_at(candidate)):
            upper = candidate
        else:
            lower = candidate
    return upper


def _refine_last_feasible_sample(
    feasible_capacity_wh: float,
    infeasible_capacity_wh: float,
    *,
    estimate_at: Callable[[float], MissionEstimate],
    max_iterations: int,
) -> float:
    """Refine an upper transition while retaining a feasible lower bound."""
    lower = feasible_capacity_wh
    upper = infeasible_capacity_wh
    for _ in range(max_iterations):
        candidate = (lower + upper) * 0.5
        if candidate == lower or candidate == upper:
            break
        if _capacity_is_feasible_or_raise(estimate_at(candidate)):
            lower = candidate
        else:
            upper = candidate
    return lower


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
    if result.minimum_capacity_wh <= 0.0:
        return 0.0
    return result.reserve_threshold_wh / result.minimum_capacity_wh * 100.0


def _wh(value: float) -> str:
    return f"{value:.1f} Wh"


def _pct(value: float) -> str:
    return f"{value:.1f}%"
