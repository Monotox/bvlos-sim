"""Seeded Monte Carlo uncertainty execution wrapping the deterministic estimator."""

import math
import random
from collections.abc import Callable, Sequence

from estimator.core.enums import EstimateStatus
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.uncertainty import MonteCarloResult, SampledOutputStats
from estimator.environment.obstacle import ObstacleProvider
from estimator.environment.population import GridPopulationProvider
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.engine import try_estimate_mission_distance_time
from estimator.execution.propagation.stats import compute_stats
from estimator.execution.propagation.wind import (
    build_component_override_wind_provider,
)
from schemas.mission import MissionPlan
from schemas.uncertainty import (
    NormalDistribution,
    UncertaintyDistribution,
    UncertaintyPlan,
)
from schemas.vehicle import VehicleProfile


def _sample(rng: random.Random, dist: UncertaintyDistribution) -> float:
    sampled = (
        rng.gauss(dist.mean, dist.std)
        if isinstance(dist, NormalDistribution)
        else rng.uniform(dist.low, dist.high)
    )
    if not math.isfinite(sampled):
        raise ValueError("sampled uncertainty value must be finite")
    return sampled


def _stats(values: list[float]) -> SampledOutputStats | None:
    return compute_stats(values)


def run_monte_carlo(
    plan: UncertaintyPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    population_provider: GridPopulationProvider | None = None,
    obstacle_provider: ObstacleProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> MonteCarloResult:
    """Run a seeded diagnostic parameter sweep and return conditional results.

    The deterministic baseline is computed first with unmodified inputs.
    Then ``plan.samples`` samples are drawn using ``plan.seed`` and each is
    run through the deterministic estimator with the sampled parameters applied.

    A sampled wind component overrides only that component of the deterministic
    provider; any unsampled component remains provider-driven. All other
    deterministic inputs are used unchanged.
    """
    params = plan.parameters

    baseline = try_estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    if baseline.status != EstimateStatus.SUCCESS:
        failure = baseline.failure
        message = (
            failure.message
            if failure is not None
            else "Baseline mission estimate failed before sampling could start."
        )
        raise ValueError(
            f"Monte Carlo sampling requires a feasible baseline: {message}"
        )

    rng = random.Random(plan.seed)

    times: list[float] = []
    reserves_wh: list[float] = []
    reserves_pct: list[float] = []
    modeled_pass_count = 0
    infeasible_count = 0
    failed = 0

    for sample_index in range(plan.samples):
        sampled_wind_east = (
            _sample(rng, params.wind_east_mps) if params.wind_east_mps else None
        )
        sampled_wind_north = (
            _sample(rng, params.wind_north_mps) if params.wind_north_mps else None
        )
        sampled_cruise_speed = (
            _sample(rng, params.cruise_speed_mps) if params.cruise_speed_mps else None
        )
        sampled_cruise_power = (
            _sample(rng, params.cruise_power_w) if params.cruise_power_w else None
        )
        sampled_battery_cap = (
            _sample(rng, params.battery_capacity_wh)
            if params.battery_capacity_wh
            else None
        )

        sample_wind_provider = _build_sample_wind_provider(
            sampled_wind_east, sampled_wind_north, wind_provider
        )
        sample_mission = _apply_mission_overrides(mission, sampled_cruise_speed)
        sample_vehicle = _apply_vehicle_overrides(
            vehicle, sampled_cruise_power, sampled_battery_cap
        )

        result = try_estimate_mission_distance_time(
            sample_mission,
            sample_vehicle,
            wind_provider=sample_wind_provider,
            terrain_provider=terrain_provider,
            population_provider=population_provider,
            obstacle_provider=obstacle_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
        if result.status == EstimateStatus.INFEASIBLE:
            infeasible_count += 1
        elif result.status == EstimateStatus.ERROR:
            failed += 1
        elif (
            result.status == EstimateStatus.SUCCESS
            and result.energy is not None
            and result.energy.is_feasible
        ):
            modeled_pass_count += 1
            times.append(result.total_time_s)
            reserves_wh.append(result.energy.reserve_at_landing_wh)
            reserves_pct.append(result.energy.reserve_at_landing_percent)
        else:
            # A nominal SUCCESS without its required energy result is not a
            # complete modeled-constraint evaluation.
            failed += 1

        if progress is not None:
            progress(sample_index + 1, plan.samples)

    evaluated_count = modeled_pass_count + infeasible_count
    modeled_pass_rate = (
        modeled_pass_count / evaluated_count if evaluated_count > 0 else None
    )

    return MonteCarloResult(
        uncertainty_id=plan.uncertainty_id,
        seed=plan.seed,
        sample_count=plan.samples,
        modeled_pass_sample_count=modeled_pass_count,
        infeasible_sample_count=infeasible_count,
        failed_sample_count=failed,
        modeled_constraint_pass_rate=modeled_pass_rate,
        total_time_s=_stats(times),
        reserve_at_mission_end_wh=_stats(reserves_wh),
        reserve_at_mission_end_percent=_stats(reserves_pct),
        baseline=baseline,
    )


def _build_sample_wind_provider(
    east: float | None,
    north: float | None,
    base_provider: WindProvider | None,
) -> WindProvider | None:
    return build_component_override_wind_provider(east, north, base_provider)


def _apply_mission_overrides(
    mission: MissionPlan,
    cruise_speed_mps: float | None,
) -> MissionPlan:
    if cruise_speed_mps is None:
        return mission
    new_defaults = mission.defaults.model_copy(
        update={"cruise_speed_mps": cruise_speed_mps}
    )
    return mission.model_copy(update={"defaults": new_defaults})


def _apply_vehicle_overrides(
    vehicle: VehicleProfile,
    cruise_power_w: float | None,
    battery_capacity_wh: float | None,
) -> VehicleProfile:
    if cruise_power_w is None and battery_capacity_wh is None:
        return vehicle
    if vehicle.energy is None:
        return vehicle
    energy_updates: dict[str, float] = {}
    if cruise_power_w is not None:
        energy_updates["cruise_power_w"] = cruise_power_w
    if battery_capacity_wh is not None:
        energy_updates["battery_capacity_wh"] = battery_capacity_wh
    new_energy = vehicle.energy.model_copy(update=energy_updates)
    return vehicle.model_copy(update={"energy": new_energy})
