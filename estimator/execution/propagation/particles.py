"""Particle track and population dataclasses for stochastic propagation."""

from dataclasses import dataclass

from estimator.core.results import MissionEstimate
from estimator.execution.propagator_ekf import EstimatedStateTracker
from estimator.execution.propagation.curves import EnergyDrainCurve
from estimator.execution.propagation.curves import PositionInterpolator
from schemas.vehicle_sensors import SensorProfile


@dataclass(slots=True)
class ParticleTrack:
    battery_capacity_wh: float
    reserve_threshold_wh: float
    energy_curve: EnergyDrainCurve
    position: PositionInterpolator
    estimated_state: EstimatedStateTracker | None = None

    @classmethod
    def from_estimate(
        cls,
        *,
        estimate: MissionEstimate,
        sensors: SensorProfile | None,
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

        return cls(
            battery_capacity_wh=estimate.energy.battery_capacity_wh,
            reserve_threshold_wh=estimate.energy.reserve_threshold_wh,
            energy_curve=energy_curve,
            position=PositionInterpolator(
                legs=estimate.legs,
                fallback_lat=init_lat,
                fallback_lon=init_lon,
            ),
            estimated_state=estimated_state,
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
        return min(self.battery_capacity_wh, max(0.0, nominal))


@dataclass(frozen=True, slots=True)
class ParticlePopulation:
    particles: tuple[ParticleTrack, ...]
    infeasible_sample_count: int = 0
    spatial_infeasible_count: int = 0
    failed_sample_count: int = 0

    @property
    def final_remaining_values(self) -> list[float]:
        return [particle.final_energy_remaining_wh for particle in self.particles]

    @property
    def t_max_s(self) -> float:
        return max(
            (particle.total_duration_s for particle in self.particles), default=0.0
        )
