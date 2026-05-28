"""Sampled-parameter draws, estimator input wiring, and particle creation."""

import random
from collections.abc import Sequence
from dataclasses import dataclass

from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.results import MissionEstimate
from estimator.environment.wind import ConstantWindProvider, WindProvider
from estimator.environment.terrain import TerrainProvider
from estimator.execution.engine import try_estimate_mission_distance_time
from estimator.execution.propagation.curves import best_position_legs
from estimator.execution.propagation.particles import ParticlePopulation, ParticleTrack
from estimator.execution.propagation.stats import sample_optional, sample_positive_optional
from schemas.mission import MissionPlan
from schemas.stochastic import StochasticPropagationPlan
from schemas.vehicle import VehicleProfile
from schemas.vehicle_controller import ControllerProfile
from schemas.vehicle_sensors import SensorProfile


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
            battery_capacity_wh=sample_positive_optional(rng, params.battery_capacity_wh),
        )


@dataclass(frozen=True, slots=True)
class EstimatorInputs:
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
            geofences=self.geofences,
            landing_zones=self.landing_zones,
        )


@dataclass(slots=True)
class ParticleSampler:
    plan: StochasticPropagationPlan
    baseline_legs: list
    estimator_inputs: EstimatorInputs
    rng: random.Random
    sensors: SensorProfile | None
    controller: ControllerProfile | None

    def run(self) -> ParticlePopulation:
        particles: list[ParticleTrack] = []
        position_legs = self.baseline_legs
        spatial_infeasible_count = 0

        for _ in range(self.plan.samples):
            sample = SampledParameters.from_plan(plan=self.plan, rng=self.rng)
            result = self.estimator_inputs.with_sample(sample).estimate()

            if is_spatial_infeasible(result):
                spatial_infeasible_count += 1
                continue

            particle = ParticleTrack.from_estimate(
                estimate=result,
                wind_east_mps=sample.wind_east_mps if sample.wind_east_mps is not None else 0.0,
                wind_north_mps=sample.wind_north_mps if sample.wind_north_mps is not None else 0.0,
                sensors=self.sensors,
                controller=self.controller,
            )
            if particle is None:
                continue

            particles.append(particle)
            position_legs = best_position_legs(position_legs, result)

        return ParticlePopulation(
            particles=tuple(particles),
            position_legs=position_legs,
            spatial_infeasible_count=spatial_infeasible_count,
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
    if east is None and north is None:
        return base_provider
    east_val = east if east is not None else 0.0
    north_val = north if north is not None else 0.0
    return ConstantWindProvider(wind_east_mps=east_val, wind_north_mps=north_val)


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
