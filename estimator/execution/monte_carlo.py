"""Seeded Monte Carlo uncertainty execution wrapping the deterministic estimator."""

import random
import statistics as stats_module
from collections.abc import Sequence

from estimator.core.errors import EstimatorError
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.uncertainty import MonteCarloResult, SampledOutputStats
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import ConstantWindProvider, WindProvider
from estimator.execution.engine import try_estimate_mission_distance_time
from schemas.mission import MissionPlan
from schemas.uncertainty import (
    NormalDistribution,
    UncertaintyDistribution,
    UncertaintyPlan,
)
from schemas.vehicle import VehicleProfile


def _sample(rng: random.Random, dist: UncertaintyDistribution) -> float:
    if isinstance(dist, NormalDistribution):
        return rng.gauss(dist.mean, dist.std)
    return rng.uniform(dist.low, dist.high)


def _stats(values: list[float]) -> SampledOutputStats | None:
    n = len(values)
    if n == 0:
        return None
    if n == 1:
        v = values[0]
        return SampledOutputStats(
            count=1, mean=v, std=0.0, min=v, p5=v, p50=v, p95=v, max=v
        )
    quantiles = stats_module.quantiles(values, n=20)
    return SampledOutputStats(
        count=n,
        mean=stats_module.mean(values),
        std=stats_module.stdev(values),
        min=min(values),
        p5=quantiles[0],
        p50=stats_module.median(values),
        p95=quantiles[18],
        max=max(values),
    )


def run_monte_carlo(
    plan: UncertaintyPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
) -> MonteCarloResult:
    """Run a seeded Monte Carlo uncertainty analysis and return aggregated results.

    The deterministic baseline is computed first with unmodified inputs.
    Then ``plan.samples`` samples are drawn using ``plan.seed`` and each is
    run through the deterministic estimator with the sampled parameters applied.

    Wind sampling creates a ConstantWindProvider per sample, overriding any
    wind-grid or layered wind provider for that sample. All other deterministic
    inputs (terrain, geofences, landing zones) are used unchanged.
    """
    params = plan.parameters

    baseline = try_estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )

    rng = random.Random(plan.seed)

    times: list[float] = []
    reserves_wh: list[float] = []
    reserves_pct: list[float] = []
    feasible_count = 0
    energy_sample_count = 0
    failed = 0

    for _ in range(plan.samples):
        sampled_wind_east = (
            _sample(rng, params.wind_east_mps) if params.wind_east_mps else None
        )
        sampled_wind_north = (
            _sample(rng, params.wind_north_mps) if params.wind_north_mps else None
        )
        sampled_cruise_speed = (
            max(0.1, _sample(rng, params.cruise_speed_mps))
            if params.cruise_speed_mps
            else None
        )
        sampled_cruise_power = (
            max(0.1, _sample(rng, params.cruise_power_w))
            if params.cruise_power_w
            else None
        )
        sampled_battery_cap = (
            max(0.1, _sample(rng, params.battery_capacity_wh))
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

        try:
            result = try_estimate_mission_distance_time(
                sample_mission,
                sample_vehicle,
                wind_provider=sample_wind_provider,
                terrain_provider=terrain_provider,
                geofences=geofences,
                landing_zones=landing_zones,
            )
        except EstimatorError:
            failed += 1
            continue

        times.append(result.total_time_s)
        if result.energy is not None:
            energy_sample_count += 1
            reserves_wh.append(result.energy.reserve_at_landing_wh)
            reserves_pct.append(result.energy.reserve_at_landing_percent)
            if result.energy.is_feasible:
                feasible_count += 1

    completed = plan.samples - failed
    feasibility_rate = (
        feasible_count / energy_sample_count if energy_sample_count > 0 else None
    )

    return MonteCarloResult(
        uncertainty_id=plan.uncertainty_id,
        seed=plan.seed,
        sample_count=plan.samples,
        completed_sample_count=completed,
        failed_sample_count=failed,
        feasibility_rate=feasibility_rate,
        total_time_s=_stats(times),
        reserve_at_landing_wh=_stats(reserves_wh),
        reserve_at_landing_percent=_stats(reserves_pct),
        baseline=baseline,
    )


def _build_sample_wind_provider(
    east: float | None,
    north: float | None,
    base_provider: WindProvider | None,
) -> WindProvider | None:
    if east is None and north is None:
        return base_provider
    east_val = east if east is not None else 0.0
    north_val = north if north is not None else 0.0
    return ConstantWindProvider(wind_east_mps=east_val, wind_north_mps=north_val)


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
