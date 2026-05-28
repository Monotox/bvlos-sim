"""Seeded stochastic state propagation over mission timelines.

Public entry point: run_stochastic_propagation.
Implementation is split across estimator/execution/propagation/.
"""

import random
from collections.abc import Sequence

from estimator.core.enums import EstimateStatus
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.environment.population import GridPopulationProvider
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.propagation.curves import PositionInterpolator
from estimator.execution.propagation.sampling import EstimatorInputs, ParticleSampler
from estimator.execution.propagation.stats import compute_stats, feasibility_rate
from estimator.execution.propagation.timeline import TimelineBuilder, reserve_threshold_wh
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
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
) -> StochasticPropagationResult:
    """Run seeded stochastic state propagation and return a timeline report."""
    estimator_inputs = EstimatorInputs(
        mission=mission,
        vehicle=vehicle,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        population_provider=population_provider,
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
        raise ValueError(f"Stochastic propagation requires a feasible baseline: {message}")

    rng = random.Random(plan.seed)
    population = ParticleSampler(
        plan=plan,
        baseline_legs=baseline.legs,
        estimator_inputs=estimator_inputs,
        rng=rng,
        sensors=vehicle.sensors,
        controller=vehicle.controller,
    ).run()

    threshold_wh = reserve_threshold_wh(baseline)
    timeline, estimation_error_timeline, cross_track_timeline = TimelineBuilder(
        population=population,
        position=PositionInterpolator(
            legs=population.position_legs,
            fallback_lat=mission.planned_home.lat,
            fallback_lon=mission.planned_home.lon,
        ),
        dt_s=plan.dt_s,
        reserve_threshold_wh=threshold_wh,
        rng=rng,
        wind_process_noise_std_mps=plan.wind_process_noise_std_mps,
        controller=vehicle.controller,
        legs=population.position_legs,
    ).build()

    # Compute final remaining after build so extra_energy_consumed_wh is fully accumulated
    final_remaining = [p.final_energy_remaining_wh for p in population.particles]

    successful_samples = len(population.particles)
    spatial_infeasible = population.spatial_infeasible_count
    return StochasticPropagationResult(
        propagation_id=plan.propagation_id,
        seed=plan.seed,
        dt_s=plan.dt_s,
        sample_count=successful_samples,
        failed_sample_count=plan.samples - successful_samples - spatial_infeasible,
        spatial_infeasible_count=spatial_infeasible,
        timeline=timeline,
        estimation_error_timeline=estimation_error_timeline,
        cross_track_timeline=cross_track_timeline,
        reserve_at_landing_wh=compute_stats(final_remaining),
        feasibility_rate=feasibility_rate(
            final_remaining,
            reserve_threshold_wh=threshold_wh,
            spatial_infeasible_count=spatial_infeasible,
        ),
        baseline=baseline,
    )
