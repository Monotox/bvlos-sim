"""Seeded stochastic state propagation over mission timelines."""

import math
import random
import statistics as stats_module
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.core.errors import EstimatorError
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.results import EnergyLegEstimate, LegEstimate, MissionEstimate
from estimator.core.uncertainty import SampledOutputStats
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import ConstantWindProvider, WindProvider
from estimator.execution.engine import try_estimate_mission_distance_time
from estimator.execution.propagator_ekf import EstimatedStateTracker
from schemas.mission import MissionPlan
from schemas.stochastic import (
    EstimationErrorTimelinePoint,
    PropagationTimelinePoint,
    StochasticPropagationPlan,
    StochasticPropagationResult,
)
from schemas.uncertainty import (
    NormalDistribution,
    UncertaintyDistribution,
)
from schemas.vehicle import VehicleProfile
from schemas.vehicle_sensors import SensorProfile


@dataclass(frozen=True, slots=True)
class _EstimatorInputs:
    mission: MissionPlan
    vehicle: VehicleProfile
    wind_provider: WindProvider | None
    terrain_provider: TerrainProvider | None
    geofences: Sequence[GeofenceZone] | None
    landing_zones: Sequence[LandingZone] | None

    def estimate(self) -> MissionEstimate:
        return try_estimate_mission_distance_time(
            self.mission,
            self.vehicle,
            wind_provider=self.wind_provider,
            terrain_provider=self.terrain_provider,
            geofences=self.geofences,
            landing_zones=self.landing_zones,
        )

    def with_sample(self, sample: "_SampledParameters") -> "_EstimatorInputs":
        return _EstimatorInputs(
            mission=_apply_mission_overrides(self.mission, sample.cruise_speed_mps),
            vehicle=_apply_vehicle_overrides(
                self.vehicle,
                sample.cruise_power_w,
                sample.battery_capacity_wh,
            ),
            wind_provider=_build_sample_wind_provider(
                sample.wind_east_mps,
                sample.wind_north_mps,
                self.wind_provider,
            ),
            terrain_provider=self.terrain_provider,
            geofences=self.geofences,
            landing_zones=self.landing_zones,
        )


@dataclass(frozen=True, slots=True)
class _SampledParameters:
    wind_east_mps: float | None
    wind_north_mps: float | None
    cruise_speed_mps: float | None
    cruise_power_w: float | None
    battery_capacity_wh: float | None

    @classmethod
    def from_plan(
        cls,
        *,
        plan: StochasticPropagationPlan,
        rng: random.Random,
    ) -> "_SampledParameters":
        params = plan.parameters
        return cls(
            wind_east_mps=_sample_optional(rng, params.wind_east_mps),
            wind_north_mps=_sample_optional(rng, params.wind_north_mps),
            cruise_speed_mps=_sample_positive_optional(rng, params.cruise_speed_mps),
            cruise_power_w=_sample_positive_optional(rng, params.cruise_power_w),
            battery_capacity_wh=_sample_positive_optional(
                rng, params.battery_capacity_wh
            ),
        )


@dataclass(frozen=True, slots=True)
class _EnergyLegDrain:
    duration_s: float
    energy_wh: float


@dataclass(frozen=True, slots=True)
class _EnergyDrainCurve:
    legs: tuple[_EnergyLegDrain, ...]

    @classmethod
    def from_estimate(cls, estimate: MissionEstimate) -> "_EnergyDrainCurve | None":
        if estimate.energy is None:
            return None

        energy_by_leg = _energy_by_leg_index(estimate.energy.legs)
        legs = tuple(
            _EnergyLegDrain(
                duration_s=leg.time_s,
                energy_wh=energy_by_leg.get(leg.leg_index, 0.0),
            )
            for leg in estimate.legs
        )
        if not legs:
            return None
        return cls(legs=legs)

    @property
    def total_duration_s(self) -> float:
        return sum(leg.duration_s for leg in self.legs)

    def energy_consumed_at(self, elapsed_time_s: float) -> float:
        elapsed = 0.0
        consumed = 0.0
        for leg in self.legs:
            next_elapsed = elapsed + leg.duration_s
            next_consumed = consumed + leg.energy_wh
            if elapsed_time_s <= next_elapsed:
                return _interpolated_energy(
                    elapsed_time_s=elapsed_time_s,
                    leg_start_s=elapsed,
                    leg_duration_s=leg.duration_s,
                    consumed_before_leg_wh=consumed,
                    leg_energy_wh=leg.energy_wh,
                    consumed_after_leg_wh=next_consumed,
                )
            elapsed = next_elapsed
            consumed = next_consumed
        return consumed


@dataclass(slots=True)
class _ParticleTrack:
    battery_capacity_wh: float
    energy_curve: _EnergyDrainCurve
    wind_east_mps: float
    wind_north_mps: float
    estimated_state: EstimatedStateTracker | None = None

    @classmethod
    def from_estimate(
        cls,
        *,
        estimate: MissionEstimate,
        sample: _SampledParameters,
        sensors: SensorProfile | None,
    ) -> "_ParticleTrack | None":
        if estimate.energy is None:
            return None

        energy_curve = _EnergyDrainCurve.from_estimate(estimate)
        if energy_curve is None:
            return None

        estimated_state = None
        if sensors is not None:
            estimated_state = EstimatedStateTracker.initial(
                true_lat=estimate.legs[0].start_lat if estimate.legs else 0.0,
                true_lon=estimate.legs[0].start_lon if estimate.legs else 0.0,
                battery_cap_wh=estimate.energy.battery_capacity_wh,
                sensors=sensors,
            )

        return cls(
            battery_capacity_wh=estimate.energy.battery_capacity_wh,
            energy_curve=energy_curve,
            wind_east_mps=_zero_when_none(sample.wind_east_mps),
            wind_north_mps=_zero_when_none(sample.wind_north_mps),
            estimated_state=estimated_state,
        )

    @property
    def total_duration_s(self) -> float:
        return self.energy_curve.total_duration_s

    @property
    def final_energy_remaining_wh(self) -> float:
        return self.energy_remaining_at(self.total_duration_s)

    def energy_remaining_at(self, elapsed_time_s: float) -> float:
        return max(
            0.0,
            self.battery_capacity_wh
            - self.energy_curve.energy_consumed_at(elapsed_time_s),
        )

    def advance_wind(
        self,
        *,
        rng: random.Random,
        step_width_s: float,
        wind_process_noise_std_mps: float,
    ) -> None:
        if step_width_s <= 0.0 or wind_process_noise_std_mps == 0.0:
            return

        std = wind_process_noise_std_mps * math.sqrt(step_width_s)
        self.wind_east_mps += rng.gauss(0.0, std)
        self.wind_north_mps += rng.gauss(0.0, std)


@dataclass(frozen=True, slots=True)
class _ParticlePopulation:
    particles: tuple[_ParticleTrack, ...]
    position_legs: list[LegEstimate]

    @property
    def final_remaining_values(self) -> list[float]:
        return [particle.final_energy_remaining_wh for particle in self.particles]

    @property
    def t_max_s(self) -> float:
        return max((particle.total_duration_s for particle in self.particles), default=0.0)


@dataclass(slots=True)
class _ParticleSampler:
    plan: StochasticPropagationPlan
    baseline_legs: list[LegEstimate]
    estimator_inputs: _EstimatorInputs
    rng: random.Random
    sensors: SensorProfile | None

    def run(self) -> _ParticlePopulation:
        particles: list[_ParticleTrack] = []
        position_legs = self.baseline_legs

        for _ in range(self.plan.samples):
            sample = _SampledParameters.from_plan(plan=self.plan, rng=self.rng)
            result = self._estimate_sample(sample)
            particle = self._particle_from_result(result, sample, self.sensors)
            if particle is None:
                continue

            particles.append(particle)
            position_legs = _position_legs(position_legs, result)

        return _ParticlePopulation(
            particles=tuple(particles),
            position_legs=position_legs,
        )

    def _estimate_sample(self, sample: _SampledParameters) -> MissionEstimate | None:
        try:
            return self.estimator_inputs.with_sample(sample).estimate()
        except EstimatorError:
            return None

    @staticmethod
    def _particle_from_result(
        result: MissionEstimate | None,
        sample: _SampledParameters,
        sensors: SensorProfile | None,
    ) -> _ParticleTrack | None:
        if result is None:
            return None
        return _ParticleTrack.from_estimate(
            estimate=result, sample=sample, sensors=sensors
        )


@dataclass(frozen=True, slots=True)
class _PositionInterpolator:
    legs: list[LegEstimate]
    fallback_lat: float
    fallback_lon: float

    def at(self, elapsed_time_s: float) -> tuple[float, float]:
        if not self.legs:
            return self.fallback_lat, self.fallback_lon

        elapsed = 0.0
        for leg in self.legs:
            next_elapsed = elapsed + leg.time_s
            if elapsed_time_s <= next_elapsed:
                return _interpolate_leg_position(
                    leg,
                    elapsed_time_s=elapsed_time_s,
                    leg_start_s=elapsed,
                )
            elapsed = next_elapsed

        last_leg = self.legs[-1]
        return last_leg.end_lat, last_leg.end_lon


@dataclass(slots=True)
class _TimelineBuilder:
    population: _ParticlePopulation
    position: _PositionInterpolator
    dt_s: float
    reserve_threshold_wh: float | None
    sample_count: int
    rng: random.Random
    wind_process_noise_std_mps: float

    def build(
        self,
    ) -> tuple[list[PropagationTimelinePoint], list[EstimationErrorTimelinePoint]]:
        if not self.population.particles:
            return [], []

        points: list[PropagationTimelinePoint] = []
        error_snapshots: list[EstimationErrorTimelinePoint] = []
        previous_time_s = 0.0
        for step_index, elapsed_time_s in enumerate(
            _timeline_steps(self.population.t_max_s, self.dt_s)
        ):
            step_width_s = elapsed_time_s - previous_time_s
            self._advance_particle_winds(step_width_s)
            self._advance_estimated_states(step_index, elapsed_time_s, step_width_s)
            points.append(self._point_at(elapsed_time_s))
            if self._has_estimated_states():
                error_point = self._estimation_error_point_at(elapsed_time_s)
                if error_point is not None:
                    error_snapshots.append(error_point)
            previous_time_s = elapsed_time_s
        return points, error_snapshots

    def _advance_particle_winds(self, step_width_s: float) -> None:
        for particle in self.population.particles:
            particle.advance_wind(
                rng=self.rng,
                step_width_s=step_width_s,
                wind_process_noise_std_mps=self.wind_process_noise_std_mps,
            )

    def _advance_estimated_states(
        self, step_index: int, elapsed_time_s: float, step_width_s: float
    ) -> None:
        for particle in self.population.particles:
            if particle.estimated_state is None:
                continue
            true_lat, true_lon = self.position.at(elapsed_time_s)
            prev_consumed = particle.energy_curve.energy_consumed_at(
                max(0.0, elapsed_time_s - step_width_s)
            )
            curr_consumed = particle.energy_curve.energy_consumed_at(elapsed_time_s)
            true_delta_wh = curr_consumed - prev_consumed
            particle.estimated_state.step(
                step_index=step_index,
                dt_s=step_width_s,
                true_lat=true_lat,
                true_lon=true_lon,
                true_energy_consumed_since_last_wh=true_delta_wh,
                rng=self.rng,
            )

    def _point_at(self, elapsed_time_s: float) -> PropagationTimelinePoint:
        true_remaining = [
            particle.energy_remaining_at(elapsed_time_s)
            for particle in self.population.particles
        ]
        if self._has_estimated_states():
            policy_remaining = [
                particle.estimated_state.est_energy_remaining_wh
                if particle.estimated_state is not None
                else particle.energy_remaining_at(elapsed_time_s)
                for particle in self.population.particles
            ]
        else:
            policy_remaining = true_remaining

        remaining_stats = _stats(true_remaining)
        if remaining_stats is None:
            raise ValueError("Timeline points require at least one particle.")

        lat_mean, lon_mean = self.position.at(elapsed_time_s)
        return PropagationTimelinePoint(
            elapsed_time_s=elapsed_time_s,
            lat_mean=lat_mean,
            lon_mean=lon_mean,
            energy_remaining_wh=remaining_stats,
            p_reserve_violation=_reserve_violation_rate(
                policy_remaining,
                reserve_threshold_wh=self.reserve_threshold_wh,
                sample_count=self.sample_count,
            ),
        )

    def _estimation_error_point_at(
        self, elapsed_time_s: float
    ) -> EstimationErrorTimelinePoint | None:
        true_lat, true_lon = self.position.at(elapsed_time_s)
        pos_errors = [
            particle.estimated_state.position_error_m(true_lat, true_lon)
            for particle in self.population.particles
            if particle.estimated_state is not None
        ]
        energy_errors = [
            particle.estimated_state.energy_error_wh(
                particle.energy_remaining_at(elapsed_time_s)
            )
            for particle in self.population.particles
            if particle.estimated_state is not None
        ]
        pos_stats = _stats(pos_errors)
        energy_stats = _stats(energy_errors)
        if pos_stats is None or energy_stats is None:
            return None
        return EstimationErrorTimelinePoint(
            elapsed_time_s=elapsed_time_s,
            position_error_m=pos_stats,
            energy_error_wh=energy_stats,
        )

    def _has_estimated_states(self) -> bool:
        return any(
            particle.estimated_state is not None for particle in self.population.particles
        )


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
    estimator_inputs = _EstimatorInputs(
        mission=mission,
        vehicle=vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    baseline = estimator_inputs.estimate()
    rng = random.Random(plan.seed)
    population = _ParticleSampler(
        plan=plan,
        baseline_legs=baseline.legs,
        estimator_inputs=estimator_inputs,
        rng=rng,
        sensors=vehicle.sensors,
    ).run()
    reserve_threshold_wh = _reserve_threshold_wh(baseline)
    final_remaining = population.final_remaining_values
    timeline, estimation_error_timeline = _TimelineBuilder(
        population=population,
        position=_PositionInterpolator(
            legs=population.position_legs,
            fallback_lat=mission.planned_home.lat,
            fallback_lon=mission.planned_home.lon,
        ),
        dt_s=plan.dt_s,
        reserve_threshold_wh=reserve_threshold_wh,
        sample_count=plan.samples,
        rng=rng,
        wind_process_noise_std_mps=plan.wind_process_noise_std_mps,
    ).build()

    return StochasticPropagationResult(
        propagation_id=plan.propagation_id,
        seed=plan.seed,
        dt_s=plan.dt_s,
        sample_count=plan.samples,
        timeline=timeline,
        estimation_error_timeline=estimation_error_timeline,
        reserve_at_landing_wh=_stats(final_remaining),
        feasibility_rate=_feasibility_rate(
            final_remaining,
            reserve_threshold_wh=reserve_threshold_wh,
            sample_count=plan.samples,
        ),
        baseline=baseline,
    )


def _sample_optional(
    rng: random.Random,
    dist: UncertaintyDistribution | None,
) -> float | None:
    if dist is None:
        return None
    return _sample(rng, dist)


def _sample_positive_optional(
    rng: random.Random,
    dist: UncertaintyDistribution | None,
) -> float | None:
    sampled = _sample_optional(rng, dist)
    if sampled is None:
        return None
    return max(0.1, sampled)


def _energy_by_leg_index(
    energy_legs: list[EnergyLegEstimate],
) -> dict[int, float]:
    return {energy_leg.leg_index: energy_leg.energy_wh for energy_leg in energy_legs}


def _interpolated_energy(
    *,
    elapsed_time_s: float,
    leg_start_s: float,
    leg_duration_s: float,
    consumed_before_leg_wh: float,
    leg_energy_wh: float,
    consumed_after_leg_wh: float,
) -> float:
    if leg_duration_s <= 0.0:
        return consumed_after_leg_wh
    fraction = (elapsed_time_s - leg_start_s) / leg_duration_s
    return consumed_before_leg_wh + (leg_energy_wh * _clamp_unit_interval(fraction))


def _interpolate_leg_position(
    leg: LegEstimate,
    *,
    elapsed_time_s: float,
    leg_start_s: float,
) -> tuple[float, float]:
    if leg.time_s <= 0.0:
        return leg.end_lat, leg.end_lon

    fraction = _clamp_unit_interval((elapsed_time_s - leg_start_s) / leg.time_s)
    return (
        leg.start_lat + ((leg.end_lat - leg.start_lat) * fraction),
        leg.start_lon + ((leg.end_lon - leg.start_lon) * fraction),
    )


def _clamp_unit_interval(value: float) -> float:
    return max(0.0, min(1.0, value))


def _zero_when_none(value: float | None) -> float:
    if value is None:
        return 0.0
    return value


def _position_legs(
    current_position_legs: list[LegEstimate],
    result: MissionEstimate,
) -> list[LegEstimate]:
    if current_position_legs:
        return current_position_legs
    return result.legs


def _reserve_threshold_wh(baseline: MissionEstimate) -> float | None:
    if baseline.energy is None:
        return None
    return baseline.energy.reserve_threshold_wh


def _timeline_steps(t_max: float, dt_s: float) -> list[float]:
    if t_max <= 0.0:
        return [0.0]

    step_count = math.floor(t_max / dt_s)
    steps = [i * dt_s for i in range(step_count + 1)]
    if t_max - steps[-1] > 1e-9:
        steps.append(t_max)
    return steps


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
