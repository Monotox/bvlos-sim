"""Timeline advancement and per-step snapshot construction."""

import math
import random
from dataclasses import dataclass

from bvlos_sim.estimator.core.results import MissionEstimate
from bvlos_sim.estimator.execution.propagation.curves import timeline_steps
from bvlos_sim.estimator.execution.propagation.particles import ParticlePopulation
from bvlos_sim.estimator.execution.propagation.stats import (
    compute_stats,
    conditional_reserve_violation_rate,
)
from bvlos_sim.schemas.stochastic import (
    CrossTrackStats,
    EstimationErrorTimelinePoint,
    PropagationTimelinePoint,
)


@dataclass(slots=True)
class TimelineBuilder:
    population: ParticlePopulation
    dt_s: float
    reserve_threshold_wh: float | None
    rng: random.Random

    def build(
        self,
    ) -> tuple[
        list[PropagationTimelinePoint],
        list[EstimationErrorTimelinePoint],
        list[CrossTrackStats],
    ]:
        if not self.population.particles:
            return [], [], []

        has_ekf = self._has_estimated_states()
        points: list[PropagationTimelinePoint] = []
        error_snapshots: list[EstimationErrorTimelinePoint] = []
        previous_time_s = 0.0
        for step_index, elapsed_time_s in enumerate(
            timeline_steps(self.population.t_max_s, self.dt_s)
        ):
            step_width_s = elapsed_time_s - previous_time_s
            self._advance_estimated_states(step_index, elapsed_time_s, step_width_s)
            points.append(self._point_at(elapsed_time_s, has_ekf=has_ekf))
            if has_ekf:
                error_point = self._estimation_error_point_at(elapsed_time_s)
                if error_point is not None:
                    error_snapshots.append(error_point)
            previous_time_s = elapsed_time_s
        return points, error_snapshots, []

    def _advance_estimated_states(
        self, step_index: int, elapsed_time_s: float, step_width_s: float
    ) -> None:
        prev_t = max(0.0, elapsed_time_s - step_width_s)
        for particle in self.population.particles:
            if particle.estimated_state is None:
                continue
            particle_time_s = min(elapsed_time_s, particle.total_duration_s)
            previous_particle_time_s = min(prev_t, particle.total_duration_s)
            particle_step_width_s = particle_time_s - previous_particle_time_s
            if elapsed_time_s > 0.0 and particle_step_width_s <= 0.0:
                continue
            true_lat, true_lon = particle.position.at(particle_time_s)
            true_delta_wh = particle.energy_curve.energy_consumed_at(
                particle_time_s
            ) - particle.energy_curve.energy_consumed_at(previous_particle_time_s)
            particle.estimated_state.step(
                step_index=step_index,
                dt_s=particle_step_width_s,
                true_lat=true_lat,
                true_lon=true_lon,
                true_energy_consumed_since_last_wh=true_delta_wh,
                rng=self.rng,
            )

    def _point_at(
        self, elapsed_time_s: float, *, has_ekf: bool
    ) -> PropagationTimelinePoint:
        true_remaining = [
            particle.energy_remaining_at(elapsed_time_s)
            for particle in self.population.particles
        ]
        if has_ekf:
            policy_remaining = [
                p.estimated_state.est_energy_remaining_wh
                if p.estimated_state is not None
                else p.energy_remaining_at(elapsed_time_s)
                for p in self.population.particles
            ]
        else:
            policy_remaining = true_remaining

        remaining_stats = compute_stats(true_remaining)
        if remaining_stats is None:
            raise ValueError("Timeline points require at least one particle.")

        true_positions = [
            particle.position.at(min(elapsed_time_s, particle.total_duration_s))
            for particle in self.population.particles
        ]
        lat_mean, lon_mean = _geographic_mean(true_positions)
        return PropagationTimelinePoint(
            elapsed_time_s=elapsed_time_s,
            route_position_centroid_lat_deg=lat_mean,
            route_position_centroid_lon_deg=lon_mean,
            energy_remaining_wh=remaining_stats,
            conditional_reserve_violation_rate=conditional_reserve_violation_rate(
                policy_remaining,
                reserve_threshold_wh=self.reserve_threshold_wh,
                reserve_thresholds_wh=[
                    particle.reserve_threshold_wh
                    for particle in self.population.particles
                ],
            ),
            contributing_sample_count=len(self.population.particles),
        )

    def _estimation_error_point_at(
        self, elapsed_time_s: float
    ) -> EstimationErrorTimelinePoint | None:
        pos_errors: list[float] = []
        energy_errors: list[float] = []
        for p in self.population.particles:
            if p.estimated_state is None:
                continue
            particle_time_s = min(elapsed_time_s, p.total_duration_s)
            true_lat, true_lon = p.position.at(particle_time_s)
            pos_errors.append(p.estimated_state.position_error_m(true_lat, true_lon))
            energy_errors.append(
                p.estimated_state.energy_error_wh(
                    p.energy_remaining_at(particle_time_s)
                )
            )
        pos_stats = compute_stats(pos_errors)
        energy_stats = compute_stats(energy_errors)
        if pos_stats is None or energy_stats is None:
            return None
        return EstimationErrorTimelinePoint(
            elapsed_time_s=elapsed_time_s,
            position_error_m=pos_stats,
            energy_error_wh=energy_stats,
        )

    def _has_estimated_states(self) -> bool:
        return any(
            particle.estimated_state is not None
            for particle in self.population.particles
        )


def reserve_threshold_wh(baseline: MissionEstimate) -> float | None:
    if baseline.energy is None:
        return None
    return baseline.energy.reserve_threshold_wh


def _geographic_mean(positions: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the spherical centroid, including across the antimeridian."""
    x = 0.0
    y = 0.0
    z = 0.0
    for lat, lon in positions:
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        cos_lat = math.cos(lat_rad)
        x += cos_lat * math.cos(lon_rad)
        y += cos_lat * math.sin(lon_rad)
        z += math.sin(lat_rad)
    horizontal = math.hypot(x, y)
    if math.hypot(horizontal, z) <= 1e-12:
        raise ValueError("geographic mean is undefined for antipodal positions")
    return math.degrees(math.atan2(z, horizontal)), math.degrees(math.atan2(y, x))
