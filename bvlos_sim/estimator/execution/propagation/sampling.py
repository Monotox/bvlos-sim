"""Sampled-parameter draws, estimator input wiring, and particle creation."""

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from bvlos_sim.estimator.core.enums import EstimateStatus
from bvlos_sim.estimator.core.geofence import GeofenceZone
from bvlos_sim.estimator.core.landing_zone import LandingZone
from bvlos_sim.estimator.core.results import MissionEstimate
from bvlos_sim.estimator.environment.obstacle import ObstacleProvider
from bvlos_sim.estimator.environment.population import GridPopulationProvider
from bvlos_sim.estimator.environment.terrain import TerrainProvider
from bvlos_sim.estimator.environment.wind import WindProvider
from bvlos_sim.estimator.execution.engine import try_estimate_mission_distance_time
from bvlos_sim.estimator.execution.propagation.particles import ParticlePopulation, ParticleTrack
from bvlos_sim.estimator.execution.propagation.stats import (
    sample_optional,
    sample_positive_optional,
)
from bvlos_sim.estimator.execution.propagation.wind import (
    build_component_override_wind_provider,
)
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.stochastic import StochasticPropagationPlan
from bvlos_sim.schemas.vehicle import VehicleProfile
from bvlos_sim.schemas.vehicle_sensors import SensorProfile


@dataclass(frozen=True, slots=True)
class SampledParameters:
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
    ) -> "SampledParameters":
        params = plan.parameters
        return cls(
            wind_east_mps=sample_optional(rng, params.wind_east_mps),
            wind_north_mps=sample_optional(rng, params.wind_north_mps),
            cruise_speed_mps=sample_positive_optional(rng, params.cruise_speed_mps),
            cruise_power_w=sample_positive_optional(rng, params.cruise_power_w),
            battery_capacity_wh=sample_positive_optional(
                rng, params.battery_capacity_wh
            ),
        )


@dataclass(frozen=True, slots=True)
class EstimatorInputs:
    mission: MissionPlan
    vehicle: VehicleProfile
    wind_provider: WindProvider | None
    terrain_provider: TerrainProvider | None
    population_provider: GridPopulationProvider | None
    obstacle_provider: ObstacleProvider | None
    geofences: Sequence[GeofenceZone] | None
    landing_zones: Sequence[LandingZone] | None

    def estimate(self) -> MissionEstimate:
        return try_estimate_mission_distance_time(
            self.mission,
            self.vehicle,
            wind_provider=self.wind_provider,
            terrain_provider=self.terrain_provider,
            population_provider=self.population_provider,
            obstacle_provider=self.obstacle_provider,
            geofences=self.geofences,
            landing_zones=self.landing_zones,
        )

    def with_sample(self, sample: SampledParameters) -> "EstimatorInputs":
        return EstimatorInputs(
            mission=apply_mission_overrides(self.mission, sample.cruise_speed_mps),
            vehicle=apply_vehicle_overrides(
                self.vehicle,
                sample.cruise_power_w,
                sample.battery_capacity_wh,
            ),
            wind_provider=build_sample_wind_provider(
                sample.wind_east_mps,
                sample.wind_north_mps,
                self.wind_provider,
            ),
            terrain_provider=self.terrain_provider,
            population_provider=self.population_provider,
            obstacle_provider=self.obstacle_provider,
            geofences=self.geofences,
            landing_zones=self.landing_zones,
        )


@dataclass(slots=True)
class ParticleSampler:
    plan: StochasticPropagationPlan
    estimator_inputs: EstimatorInputs
    rng: random.Random
    sensors: SensorProfile | None
    progress: Callable[[int, int], None] | None = None

    def run(self) -> ParticlePopulation:
        particles: list[ParticleTrack] = []
        infeasible_sample_count = 0
        spatial_infeasible_count = 0
        failed_sample_count = 0

        for sample_index in range(self.plan.samples):
            try:
                sample = SampledParameters.from_plan(plan=self.plan, rng=self.rng)
                result = self.estimator_inputs.with_sample(sample).estimate()
            except (ArithmeticError, ValueError):
                failed_sample_count += 1
                if self.progress is not None:
                    self.progress(sample_index + 1, self.plan.samples)
                continue

            spatial_infeasible = is_spatial_infeasible(result)
            if result.status == EstimateStatus.INFEASIBLE or spatial_infeasible:
                infeasible_sample_count += 1
                if spatial_infeasible:
                    spatial_infeasible_count += 1
            elif result.status == EstimateStatus.ERROR:
                failed_sample_count += 1
            else:
                particle = ParticleTrack.from_estimate(
                    estimate=result,
                    sensors=self.sensors,
                )
                if particle is not None:
                    particles.append(particle)
                else:
                    failed_sample_count += 1

            if self.progress is not None:
                self.progress(sample_index + 1, self.plan.samples)

        return ParticlePopulation(
            particles=tuple(particles),
            infeasible_sample_count=infeasible_sample_count,
            spatial_infeasible_count=spatial_infeasible_count,
            failed_sample_count=failed_sample_count,
        )


def is_spatial_infeasible(estimate: MissionEstimate) -> bool:
    if estimate.geofence is not None and not estimate.geofence.is_feasible:
        return True
    if estimate.landing_zone is not None and not estimate.landing_zone.is_feasible:
        return True
    return False


def build_sample_wind_provider(
    east: float | None,
    north: float | None,
    base_provider: WindProvider | None,
) -> WindProvider | None:
    return build_component_override_wind_provider(east, north, base_provider)


def apply_mission_overrides(
    mission: MissionPlan,
    cruise_speed_mps: float | None,
) -> MissionPlan:
    if cruise_speed_mps is None:
        return mission
    new_defaults = mission.defaults.model_copy(
        update={"cruise_speed_mps": cruise_speed_mps}
    )
    return mission.model_copy(update={"defaults": new_defaults})


def apply_vehicle_overrides(
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
