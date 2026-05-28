"""Particle track and population dataclasses for stochastic propagation."""

import math
import random
from dataclasses import dataclass

from estimator.core.results import LegEstimate, MissionEstimate
from estimator.execution.propagator_ekf import EstimatedStateTracker
from estimator.execution.tracking_controller import ControllerState
from estimator.execution.propagation.curves import EnergyDrainCurve
from schemas.vehicle_controller import ControllerProfile
from schemas.vehicle_sensors import SensorProfile


@dataclass(slots=True)
class ParticleTrack:
    battery_capacity_wh: float
    energy_curve: EnergyDrainCurve
    wind_east_mps: float
    wind_north_mps: float
    estimated_state: EstimatedStateTracker | None = None
    controller_state: ControllerState | None = None

    @classmethod
    def from_estimate(
        cls,
        *,
        estimate: MissionEstimate,
        wind_east_mps: float,
        wind_north_mps: float,
        sensors: SensorProfile | None,
        controller: ControllerProfile | None,
    ) -> "ParticleTrack | None":
        if estimate.energy is None:
            return None
        energy_curve = EnergyDrainCurve.from_estimate(estimate)
        if energy_curve is None:
            return None

        init_lat = estimate.legs[0].start_lat if estimate.legs else 0.0
        init_lon = estimate.legs[0].start_lon if estimate.legs else 0.0

        estimated_state = None
        if sensors is not None:
            estimated_state = EstimatedStateTracker.initial(
                true_lat=init_lat,
                true_lon=init_lon,
                battery_cap_wh=estimate.energy.battery_capacity_wh,
                sensors=sensors,
            )

        controller_state = None
        if controller is not None and sensors is not None:
            controller_state = ControllerState(true_lat=init_lat, true_lon=init_lon)

        return cls(
            battery_capacity_wh=estimate.energy.battery_capacity_wh,
            energy_curve=energy_curve,
            wind_east_mps=wind_east_mps,
            wind_north_mps=wind_north_mps,
            estimated_state=estimated_state,
            controller_state=controller_state,
        )

    @property
    def total_duration_s(self) -> float:
        return self.energy_curve.total_duration_s

    @property
    def final_energy_remaining_wh(self) -> float:
        return self.energy_remaining_at(self.total_duration_s)

    def energy_remaining_at(self, elapsed_time_s: float) -> float:
        nominal = self.battery_capacity_wh - self.energy_curve.energy_consumed_at(
            elapsed_time_s
        )
        extra = (
            self.controller_state.extra_energy_consumed_wh
            if self.controller_state is not None
            else 0.0
        )
        return max(0.0, nominal - extra)

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
class ParticlePopulation:
    particles: tuple[ParticleTrack, ...]
    position_legs: list[LegEstimate]
    spatial_infeasible_count: int = 0

    @property
    def final_remaining_values(self) -> list[float]:
        return [particle.final_energy_remaining_wh for particle in self.particles]

    @property
    def t_max_s(self) -> float:
        return max(
            (particle.total_duration_s for particle in self.particles), default=0.0
        )
