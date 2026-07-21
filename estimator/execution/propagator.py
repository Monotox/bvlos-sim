"""Seeded stochastic state propagation over mission timelines.

Public entry point: run_stochastic_propagation.
Implementation is split across estimator/execution/propagation/.
"""

import random
from collections.abc import Callable, Sequence

from estimator.core.enums import EstimateStatus
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.environment.obstacle import ObstacleProvider
from estimator.environment.population import GridPopulationProvider
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.propagation.sampling import EstimatorInputs, ParticleSampler
from estimator.execution.propagation.stats import (
    compute_stats,
    modeled_constraint_pass_rate,
)
from estimator.execution.propagation.timeline import (
    TimelineBuilder,
    reserve_threshold_wh,
)
from schemas.mission import MissionPlan
from schemas.stochastic import StochasticPropagationPlan, StochasticPropagationResult
from schemas.vehicle import VehicleProfile


def run_stochastic_propagation(
    plan: StochasticPropagationPlan,
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
) -> StochasticPropagationResult:
    """Run a seeded open-loop parameter sweep and return diagnostic timelines."""
    if plan.wind_process_noise_std_mps != 0.0:
        raise ValueError(
            "stochastic.v2 does not support process-wind dynamics; "
            "wind_process_noise_std_mps must be 0.0"
        )
    if vehicle.controller is not None:
        raise ValueError(
            "stochastic.v2 does not support closed-loop controller propagation; "
            "remove vehicle.controller and treat the output as an open-loop diagnostic"
        )

    estimator_inputs = EstimatorInputs(
        mission=mission,
        vehicle=vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    baseline = estimator_inputs.estimate()
    if baseline.status != EstimateStatus.SUCCESS:
        failure = baseline.failure
        message = (
            failure.message
            if failure is not None
            else "Baseline mission estimate failed before propagation could start."
        )
        raise ValueError(
            f"Stochastic propagation requires a feasible baseline: {message}"
        )

    rng = random.Random(plan.seed)
    population = ParticleSampler(
        plan=plan,
        estimator_inputs=estimator_inputs,
        rng=rng,
        sensors=vehicle.sensors,
        progress=progress,
    ).run()

    threshold_wh = reserve_threshold_wh(baseline)
    timeline, estimation_error_timeline, cross_track_timeline = TimelineBuilder(
        population=population,
        dt_s=plan.dt_s,
        reserve_threshold_wh=threshold_wh,
        rng=rng,
    ).build()

    final_remaining = [p.final_energy_remaining_wh for p in population.particles]

    successful_samples = len(population.particles)
    infeasible_samples = population.infeasible_sample_count
    spatial_infeasible = population.spatial_infeasible_count
    accounted_samples = (
        successful_samples + infeasible_samples + population.failed_sample_count
    )
    if accounted_samples != plan.samples:
        raise RuntimeError(
            "Stochastic sample accounting invariant failed: "
            f"{accounted_samples} outcomes for {plan.samples} requested samples."
        )
    return StochasticPropagationResult(
        propagation_id=plan.propagation_id,
        seed=plan.seed,
        dt_s=plan.dt_s,
        requested_sample_count=plan.samples,
        sample_count=successful_samples,
        infeasible_sample_count=infeasible_samples,
        failed_sample_count=population.failed_sample_count,
        spatial_infeasible_count=spatial_infeasible,
        timeline=timeline,
        estimation_error_timeline=estimation_error_timeline,
        cross_track_timeline=cross_track_timeline,
        reserve_at_mission_end_wh=compute_stats(final_remaining),
        modeled_constraint_pass_rate=modeled_constraint_pass_rate(
            successful_samples,
            infeasible_sample_count=infeasible_samples,
        ),
        baseline=baseline,
    )
