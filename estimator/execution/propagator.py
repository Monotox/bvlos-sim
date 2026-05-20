"""Seeded stochastic state propagation over mission timelines."""

import math
import random
import statistics as stats_module
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.core.errors import EstimatorError
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.results import EnergyLegEstimate, LegEstimate
from estimator.core.uncertainty import SampledOutputStats
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import ConstantWindProvider, WindProvider
from estimator.execution.engine import try_estimate_mission_distance_time
from schemas.mission import MissionPlan
from schemas.stochastic import (
    PropagationTimelinePoint,
    StochasticPropagationPlan,
    StochasticPropagationResult,
)
from schemas.uncertainty import (
    NormalDistribution,
    UncertaintyDistribution,
)
from schemas.vehicle import VehicleProfile


@dataclass
class _ParticleTrack:
    battery_capacity_wh: float
    leg_pairs: list[tuple[float, float]]
    wind_east_mps: float
    wind_north_mps: float


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


def run_stochastic_propagation(
    plan: StochasticPropagationPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
) -> StochasticPropagationResult:
    """Run seeded stochastic state propagation and return a timeline report."""
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
    particles: list[_ParticleTrack] = []
    position_legs = baseline.legs

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
            continue

        particle = _particle_from_estimate(
            result_legs=result.legs,
            energy_legs=result.energy.legs if result.energy is not None else None,
            battery_capacity_wh=(
                result.energy.battery_capacity_wh if result.energy is not None else None
            ),
            sampled_wind_east=sampled_wind_east,
            sampled_wind_north=sampled_wind_north,
        )
        if particle is not None:
            particles.append(particle)
            if not position_legs:
                position_legs = result.legs

    final_remaining = [
        _energy_remaining_at(particle, _particle_total_duration_s(particle))
        for particle in particles
    ]
    reserve_threshold_wh = (
        baseline.energy.reserve_threshold_wh if baseline.energy is not None else None
    )
    feasibility_rate = _feasibility_rate(
        final_remaining,
        reserve_threshold_wh=reserve_threshold_wh,
        sample_count=plan.samples,
    )

    timeline = _build_timeline(
        particles,
        baseline_legs=position_legs,
        fallback_lat=mission.planned_home.lat,
        fallback_lon=mission.planned_home.lon,
        dt_s=plan.dt_s,
        reserve_threshold_wh=reserve_threshold_wh,
        sample_count=plan.samples,
        rng=rng,
        wind_process_noise_std_mps=plan.wind_process_noise_std_mps,
    )

    return StochasticPropagationResult(
        propagation_id=plan.propagation_id,
        seed=plan.seed,
        dt_s=plan.dt_s,
        sample_count=plan.samples,
        timeline=timeline,
        reserve_at_landing_wh=_stats(final_remaining),
        feasibility_rate=feasibility_rate,
        baseline=baseline,
    )


def _particle_from_estimate(
    *,
    result_legs: list[LegEstimate],
    energy_legs: list[EnergyLegEstimate] | None,
    battery_capacity_wh: float | None,
    sampled_wind_east: float | None,
    sampled_wind_north: float | None,
) -> _ParticleTrack | None:
    if energy_legs is None or battery_capacity_wh is None:
        return None

    energy_by_leg = {
        energy_leg.leg_index: energy_leg.energy_wh for energy_leg in energy_legs
    }
    leg_pairs = [
        (leg.time_s, energy_by_leg.get(leg.leg_index, 0.0)) for leg in result_legs
    ]
    if not leg_pairs:
        return None

    return _ParticleTrack(
        battery_capacity_wh=battery_capacity_wh,
        leg_pairs=leg_pairs,
        wind_east_mps=sampled_wind_east if sampled_wind_east is not None else 0.0,
        wind_north_mps=sampled_wind_north if sampled_wind_north is not None else 0.0,
    )


def _build_timeline(
    particles: list[_ParticleTrack],
    *,
    baseline_legs: list[LegEstimate],
    fallback_lat: float,
    fallback_lon: float,
    dt_s: float,
    reserve_threshold_wh: float | None,
    sample_count: int,
    rng: random.Random,
    wind_process_noise_std_mps: float,
) -> list[PropagationTimelinePoint]:
    if not particles:
        return []

    t_max = max(_particle_total_duration_s(particle) for particle in particles)
    timeline: list[PropagationTimelinePoint] = []
    previous_time_s = 0.0

    for elapsed_time_s in _timeline_steps(t_max, dt_s):
        step_width_s = elapsed_time_s - previous_time_s
        _advance_particle_winds(
            particles,
            rng=rng,
            step_width_s=step_width_s,
            wind_process_noise_std_mps=wind_process_noise_std_mps,
        )
        remaining_values = [
            _energy_remaining_at(particle, elapsed_time_s) for particle in particles
        ]
        remaining_stats = _stats(remaining_values)
        if remaining_stats is None:
            continue

        lat_mean, lon_mean = _position_at(
            baseline_legs,
            elapsed_time_s,
            fallback_lat=fallback_lat,
            fallback_lon=fallback_lon,
        )
        timeline.append(
            PropagationTimelinePoint(
                elapsed_time_s=elapsed_time_s,
                lat_mean=lat_mean,
                lon_mean=lon_mean,
                energy_remaining_wh=remaining_stats,
                p_reserve_violation=_reserve_violation_rate(
                    remaining_values,
                    reserve_threshold_wh=reserve_threshold_wh,
                    sample_count=sample_count,
                ),
            )
        )
        previous_time_s = elapsed_time_s

    return timeline


def _timeline_steps(t_max: float, dt_s: float) -> list[float]:
    if t_max <= 0.0:
        return [0.0]

    step_count = math.floor(t_max / dt_s)
    steps = [i * dt_s for i in range(step_count + 1)]
    if t_max - steps[-1] > 1e-9:
        steps.append(t_max)
    return steps


def _particle_total_duration_s(particle: _ParticleTrack) -> float:
    return sum(duration_s for duration_s, _energy_wh in particle.leg_pairs)


def _energy_remaining_at(particle: _ParticleTrack, elapsed_time_s: float) -> float:
    return max(
        0.0,
        particle.battery_capacity_wh
        - _energy_consumed_at(particle.leg_pairs, elapsed_time_s),
    )


def _energy_consumed_at(
    leg_pairs: list[tuple[float, float]],
    elapsed_time_s: float,
) -> float:
    elapsed = 0.0
    consumed = 0.0
    for duration_s, energy_wh in leg_pairs:
        next_elapsed = elapsed + duration_s
        next_consumed = consumed + energy_wh
        if elapsed_time_s <= next_elapsed:
            if duration_s <= 0.0:
                return next_consumed
            fraction = (elapsed_time_s - elapsed) / duration_s
            return consumed + (energy_wh * max(0.0, min(1.0, fraction)))
        elapsed = next_elapsed
        consumed = next_consumed
    return consumed


def _position_at(
    legs: list[LegEstimate],
    elapsed_time_s: float,
    *,
    fallback_lat: float,
    fallback_lon: float,
) -> tuple[float, float]:
    if not legs:
        return fallback_lat, fallback_lon

    elapsed = 0.0
    for leg in legs:
        next_elapsed = elapsed + leg.time_s
        if elapsed_time_s <= next_elapsed:
            if leg.time_s <= 0.0:
                return leg.end_lat, leg.end_lon
            fraction = (elapsed_time_s - elapsed) / leg.time_s
            clamped = max(0.0, min(1.0, fraction))
            return (
                leg.start_lat + ((leg.end_lat - leg.start_lat) * clamped),
                leg.start_lon + ((leg.end_lon - leg.start_lon) * clamped),
            )
        elapsed = next_elapsed

    last_leg = legs[-1]
    return last_leg.end_lat, last_leg.end_lon


def _advance_particle_winds(
    particles: list[_ParticleTrack],
    *,
    rng: random.Random,
    step_width_s: float,
    wind_process_noise_std_mps: float,
) -> None:
    if step_width_s <= 0.0 or wind_process_noise_std_mps == 0.0:
        return

    std = wind_process_noise_std_mps * math.sqrt(step_width_s)
    for particle in particles:
        particle.wind_east_mps += rng.gauss(0.0, std)
        particle.wind_north_mps += rng.gauss(0.0, std)


def _reserve_violation_rate(
    values: list[float],
    *,
    reserve_threshold_wh: float | None,
    sample_count: int,
) -> float:
    if reserve_threshold_wh is None:
        return 0.0
    violation_count = sum(value < reserve_threshold_wh for value in values)
    return violation_count / sample_count


def _feasibility_rate(
    values: list[float],
    *,
    reserve_threshold_wh: float | None,
    sample_count: int,
) -> float:
    if reserve_threshold_wh is None:
        return 0.0
    feasible_count = sum(value >= reserve_threshold_wh for value in values)
    return feasible_count / sample_count


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
