"""Mission distance/time estimator orchestration.

The public estimator API stays here, while context assembly, route-item
dispatch, and leg estimation are delegated to smaller execution modules.
"""

from collections.abc import Sequence

from estimator.core.enums import EstimateStatus, FailureKind
from estimator.core.errors import EstimatorError
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.options import EstimationOptions
from estimator.core.results import (
    EnergyEstimate,
    EstimatorFailure,
    GeofenceEstimate,
    LandingZoneEstimate,
    MissionEstimate,
)
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.context_builder import build_estimation_context
from estimator.execution.energy import evaluate_energy_feasibility
from estimator.execution.executors import execute_route_item
from estimator.execution.geofence import evaluate_geofence_feasibility
from estimator.execution.landing_zone import evaluate_landing_zone_reachability
from estimator.execution.rules import validate_global_constraints
from estimator.execution.runtime import EstimationContext
from estimator.execution.runtime.failure_translation import error_from_failure
from estimator.execution.totals import sum_totals
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile


def _raise_feasibility_failure(
    failure: EstimatorFailure | None,
    context: EstimationContext,
    *,
    energy: EnergyEstimate | None = None,
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
) -> None:
    if failure is None:
        return
    raise error_from_failure(
        failure,
        partial_legs=context.route_legs,
        energy=energy,
        geofence=geofence,
        landing_zone=landing_zone,
        totals_are_partial=False,
        warnings=context.warnings,
        metadata=context.metadata,
    )


def run_estimation(
    context: EstimationContext,
    *,
    lz_unavailability: list[frozenset[str]] | None = None,
) -> MissionEstimate:
    """Execute the estimator against a prepared context."""

    validate_global_constraints(context)

    for route_item_index, item in enumerate(context.mission.route):
        execute_route_item(
            context,
            item,
            route_item_index=route_item_index,
        )

    totals = sum_totals(context.route_legs)
    energy_evaluation = evaluate_energy_feasibility(context)
    _raise_feasibility_failure(
        energy_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
    )

    geofence_evaluation = evaluate_geofence_feasibility(context)
    _raise_feasibility_failure(
        geofence_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        geofence=geofence_evaluation.geofence,
    )

    landing_zone_evaluation = evaluate_landing_zone_reachability(
        context,
        energy_evaluation.energy,
        unavailable_zone_ids_by_state=lz_unavailability,
    )
    _raise_feasibility_failure(
        landing_zone_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
    )

    return MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=totals.horizontal_distance_m,
        total_vertical_distance_m=totals.vertical_distance_m,
        total_path_distance_m=totals.path_distance_m,
        total_time_s=totals.time_s,
        totals_are_partial=False,
        legs=context.route_legs,
        energy=energy_evaluation.energy,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
        warnings=context.warnings,
        failure=None,
        metadata=context.metadata,
    )


def estimate_mission_distance_time(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    options: EstimationOptions | None = None,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    lz_unavailability: list[frozenset[str]] | None = None,
) -> MissionEstimate:
    context = build_estimation_context(
        mission,
        vehicle,
        options=options,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    return run_estimation(context, lz_unavailability=lz_unavailability)


def try_estimate_mission_distance_time(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    options: EstimationOptions | None = None,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    lz_unavailability: list[frozenset[str]] | None = None,
) -> MissionEstimate:
    try:
        return estimate_mission_distance_time(
            mission,
            vehicle,
            options=options,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
            lz_unavailability=lz_unavailability,
        )
    except EstimatorError as exc:
        totals = sum_totals(exc.partial_legs)
        return MissionEstimate(
            status=(
                EstimateStatus.INFEASIBLE
                if exc.failure.kind == FailureKind.INFEASIBLE
                else EstimateStatus.ERROR
            ),
            total_horizontal_distance_m=totals.horizontal_distance_m,
            total_vertical_distance_m=totals.vertical_distance_m,
            total_path_distance_m=totals.path_distance_m,
            total_time_s=totals.time_s,
            totals_are_partial=exc.totals_are_partial,
            legs=exc.partial_legs,
            energy=exc.energy,
            geofence=exc.geofence,
            landing_zone=exc.landing_zone,
            warnings=exc.warnings,
            failure=exc.failure,
            metadata=exc.metadata,
        )
