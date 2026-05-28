"""Timeline advancement and per-step snapshot construction."""

import random
from dataclasses import dataclass

from estimator.core.results import LegEstimate, MissionEstimate
from estimator.execution.tracking_controller import advance_true_state
from estimator.execution.propagation.curves import PositionInterpolator, timeline_steps
from estimator.execution.propagation.particles import ParticlePopulation
from estimator.execution.propagation.stats import compute_stats, reserve_violation_rate
from schemas.stochastic import (
    CrossTrackStats,
    EstimationErrorTimelinePoint,
    PropagationTimelinePoint,
)
from schemas.vehicle_controller import ControllerProfile


@dataclass(slots=True)
class TimelineBuilder:
    population: ParticlePopulation
    position: PositionInterpolator
    dt_s: float
    reserve_threshold_wh: float | None
    rng: random.Random
    wind_process_noise_std_mps: float
    controller: ControllerProfile | None
    legs: list[LegEstimate]

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
        has_ctrl = self._has_controller_states()
        points: list[PropagationTimelinePoint] = []
        error_snapshots: list[EstimationErrorTimelinePoint] = []
        xte_snapshots: list[CrossTrackStats] = []
        previous_time_s = 0.0
        for step_index, elapsed_time_s in enumerate(
            timeline_steps(self.population.t_max_s, self.dt_s)
        ):
            step_width_s = elapsed_time_s - previous_time_s
            self._advance_particle_winds(step_width_s)
            # Controller advances true position before EKF sees new truth
            if has_ctrl:
                self._advance_controller_states(elapsed_time_s, step_width_s)
            self._advance_estimated_states(step_index, elapsed_time_s, step_width_s)
            points.append(self._point_at(elapsed_time_s, has_ekf=has_ekf))
            if has_ekf:
                error_point = self._estimation_error_point_at(elapsed_time_s, has_ctrl=has_ctrl)
                if error_point is not None:
                    error_snapshots.append(error_point)
            if has_ctrl:
                xte_point = self._cross_track_point_at(elapsed_time_s)
                if xte_point is not None:
                    xte_snapshots.append(xte_point)
            previous_time_s = elapsed_time_s
        return points, error_snapshots, xte_snapshots

    def _advance_particle_winds(self, step_width_s: float) -> None:
        for particle in self.population.particles:
            particle.advance_wind(
                rng=self.rng,
                step_width_s=step_width_s,
                wind_process_noise_std_mps=self.wind_process_noise_std_mps,
            )

    def _advance_controller_states(
        self, elapsed_time_s: float, step_width_s: float
    ) -> None:
        if self.controller is None:
            return
        leg = active_leg_at(self.legs, elapsed_time_s)
        if leg is None:
            return
        nominal_speed = leg.path_distance_m / leg.time_s if leg.time_s > 0 else 1.0
        prev_t = max(0.0, elapsed_time_s - step_width_s)

        for particle in self.population.particles:
            cs = particle.controller_state
            if cs is None or particle.estimated_state is None:
                continue
            nominal_energy_step = (
                particle.energy_curve.energy_consumed_at(elapsed_time_s)
                - particle.energy_curve.energy_consumed_at(prev_t)
            )
            advance_true_state(
                est_lat=particle.estimated_state.est_lat,
                est_lon=particle.estimated_state.est_lon,
                nominal_speed_mps=nominal_speed,
                nominal_energy_step_wh=nominal_energy_step,
                dt_s=step_width_s,
                profile=self.controller,
                state=cs,
                seg_start_lat=leg.start_lat,
                seg_start_lon=leg.start_lon,
                seg_end_lat=leg.end_lat,
                seg_end_lon=leg.end_lon,
            )

    def _advance_estimated_states(
        self, step_index: int, elapsed_time_s: float, step_width_s: float
    ) -> None:
        planned_pos = self.position.at(elapsed_time_s)
        prev_t = max(0.0, elapsed_time_s - step_width_s)
        for particle in self.population.particles:
            if particle.estimated_state is None:
                continue
            true_lat, true_lon = (
                (particle.controller_state.true_lat, particle.controller_state.true_lon)
                if particle.controller_state is not None
                else planned_pos
            )
            true_delta_wh = (
                particle.energy_curve.energy_consumed_at(elapsed_time_s)
                - particle.energy_curve.energy_consumed_at(prev_t)
            )
            particle.estimated_state.step(
                step_index=step_index,
                dt_s=step_width_s,
                true_lat=true_lat,
                true_lon=true_lon,
                true_energy_consumed_since_last_wh=true_delta_wh,
                rng=self.rng,
            )

    def _point_at(self, elapsed_time_s: float, *, has_ekf: bool) -> PropagationTimelinePoint:
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

        lat_mean, lon_mean = self.position.at(elapsed_time_s)
        return PropagationTimelinePoint(
            elapsed_time_s=elapsed_time_s,
            lat_mean=lat_mean,
            lon_mean=lon_mean,
            energy_remaining_wh=remaining_stats,
            p_reserve_violation=reserve_violation_rate(
                policy_remaining,
                reserve_threshold_wh=self.reserve_threshold_wh,
            ),
        )

    def _estimation_error_point_at(
        self, elapsed_time_s: float, *, has_ctrl: bool
    ) -> EstimationErrorTimelinePoint | None:
        planned_pos = self.position.at(elapsed_time_s)
        pos_errors: list[float] = []
        energy_errors: list[float] = []
        for p in self.population.particles:
            if p.estimated_state is None:
                continue
            true_lat, true_lon = (
                (p.controller_state.true_lat, p.controller_state.true_lon)
                if has_ctrl and p.controller_state is not None
                else planned_pos
            )
            pos_errors.append(p.estimated_state.position_error_m(true_lat, true_lon))
            energy_errors.append(
                p.estimated_state.energy_error_wh(p.energy_remaining_at(elapsed_time_s))
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

    def _cross_track_point_at(self, elapsed_time_s: float) -> CrossTrackStats | None:
        xte_vals: list[float] = []
        ate_vals: list[float] = []
        excess_vals: list[float] = []
        for p in self.population.particles:
            if p.controller_state is None:
                continue
            xte_vals.append(abs(p.controller_state.cross_track_error_m))
            ate_vals.append(p.controller_state.along_track_error_m)
            excess_vals.append(p.controller_state.path_length_excess_m)
        xte_stats = compute_stats(xte_vals)
        ate_stats = compute_stats(ate_vals)
        excess_stats = compute_stats(excess_vals)
        if xte_stats is None or ate_stats is None or excess_stats is None:
            return None
        return CrossTrackStats(
            elapsed_time_s=elapsed_time_s,
            cross_track_error_m=xte_stats,
            along_track_error_m=ate_stats,
            path_length_excess_m=excess_stats,
        )

    def _has_estimated_states(self) -> bool:
        return any(
            particle.estimated_state is not None for particle in self.population.particles
        )

    def _has_controller_states(self) -> bool:
        return any(
            particle.controller_state is not None for particle in self.population.particles
        )


def active_leg_at(legs: list[LegEstimate], elapsed_time_s: float) -> LegEstimate | None:
    elapsed = 0.0
    for leg in legs:
        if elapsed_time_s <= elapsed + leg.time_s:
            return leg
        elapsed += leg.time_s
    return legs[-1] if legs else None


def reserve_threshold_wh(baseline: MissionEstimate) -> float | None:
    if baseline.energy is None:
        return None
    return baseline.energy.reserve_threshold_wh
