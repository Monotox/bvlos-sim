"""Mission distance/time estimator orchestration.

The public estimator API stays here, while context assembly, route-item
dispatch, and leg estimation are delegated to smaller execution modules.
"""

from collections.abc import Sequence

from bvlos_sim.estimator.core.enums import EstimateStatus, FailureKind, WarningCode
from bvlos_sim.estimator.core.errors import EstimatorError
from bvlos_sim.estimator.core.geofence import GeofenceZone
from bvlos_sim.estimator.core.landing_zone import LandingZone
from bvlos_sim.estimator.core.options import EstimationOptions
from bvlos_sim.estimator.core.results import (
    EnergyEstimate,
    EstimatorFailure,
    EstimatorWarning,
    GeofenceEstimate,
    LandingZoneEstimate,
    LegEstimate,
    LinkEstimate,
    MissionEstimate,
    ObstacleEstimate,
    ResourceEstimate,
    WeatherEstimate,
)
from bvlos_sim.estimator.environment.obstacle import ObstacleProvider
from bvlos_sim.estimator.environment.population import GridPopulationProvider
from bvlos_sim.estimator.environment.terrain import TerrainProvider
from bvlos_sim.estimator.environment.wind import WindProvider
from bvlos_sim.estimator.execution.context_builder import build_estimation_context
from bvlos_sim.estimator.execution.energy import evaluate_energy_feasibility
from bvlos_sim.estimator.execution.executors import execute_route_item
from bvlos_sim.estimator.execution.geofence import evaluate_geofence_feasibility
from bvlos_sim.estimator.execution.ground_risk import compute_ground_risk
from bvlos_sim.estimator.execution.landing_zone import evaluate_landing_zone_reachability
from bvlos_sim.estimator.execution.obstacle import evaluate_obstacle_clearance
from bvlos_sim.estimator.execution.resource_link import (
    evaluate_link_feasibility,
    evaluate_resource_feasibility,
    selected_resource_rth_is_feasible,
)
from bvlos_sim.estimator.execution.rules import validate_global_constraints
from bvlos_sim.estimator.execution.runtime import EstimationContext
from bvlos_sim.estimator.execution.weather import evaluate_weather_feasibility
from bvlos_sim.estimator.execution.runtime.failure_translation import error_from_failure
from bvlos_sim.estimator.execution.totals import sum_totals
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.vehicle import VehicleProfile
from bvlos_sim.schemas.vehicle_enums import CalibrationStatus

# Coefficient provenance that counts as validated. Anything else, including an
# undeclared status, raises ENERGY_MODEL_UNCALIBRATED.
_CALIBRATED_STATUSES = frozenset(
    {CalibrationStatus.MANUFACTURER_DERIVED, CalibrationStatus.LOG_CALIBRATED}
)


def _raise_feasibility_failure(
    failure: EstimatorFailure | None,
    context: EstimationContext,
    *,
    energy: EnergyEstimate | None = None,
    resource: ResourceEstimate | None = None,
    link: LinkEstimate | None = None,
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
    obstacle: ObstacleEstimate | None = None,
    weather: WeatherEstimate | None = None,
) -> None:
    if failure is None:
        return
    raise error_from_failure(
        failure,
        partial_legs=context.route_legs,
        energy=energy,
        resource=resource,
        link=link,
        geofence=geofence,
        landing_zone=landing_zone,
        obstacle=obstacle,
        weather=weather,
        totals_are_partial=False,
        warnings=context.warnings,
        metadata=context.metadata,
    )


def _rth_is_feasible(
    energy: EnergyEstimate | None,
    resource: ResourceEstimate | None,
    *,
    vehicle: VehicleProfile,
    route_legs: list[LegEstimate],
) -> bool | None:
    if resource is not None:
        return selected_resource_rth_is_feasible(
            vehicle,
            route_legs,
            energy,
            resource,
        )
    if energy is None or energy.rth_reserve_timeline is None:
        return None
    return all(point.is_feasible for point in energy.rth_reserve_timeline)


def run_estimation(
    context: EstimationContext,
    *,
    lz_unavailability: list[frozenset[str]] | None = None,
) -> MissionEstimate:
    """Execute the estimator against a prepared context."""

    validate_global_constraints(context)
    _check_route_structure(context)

    for route_item_index, item in enumerate(context.mission.route):
        execute_route_item(
            context,
            item,
            route_item_index=route_item_index,
        )

    totals = sum_totals(context.route_legs)
    _check_max_wind(context)
    _check_energy_model_calibration(context)
    explicit_resource_systems = bool(context.vehicle.resource_systems)
    energy_evaluation = evaluate_energy_feasibility(
        context,
        enforce_battery_capacity=not explicit_resource_systems,
        enforce_rth_reserve=not explicit_resource_systems,
    )
    _raise_feasibility_failure(
        energy_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
    )

    resource_evaluation = evaluate_resource_feasibility(
        context,
        energy_evaluation.energy,
    )
    _raise_feasibility_failure(
        resource_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        resource=resource_evaluation.resource,
    )

    link_evaluation = evaluate_link_feasibility(context)
    _raise_feasibility_failure(
        link_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
    )

    if context.geofences is not None and not context.geofences:
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.GEOFENCE_ZERO_ZONES,
                message=(
                    "A geofence file is configured but contains zero zones; "
                    "the clearance check evaluated no airspace. Verify the "
                    "fetch produced real coverage before trusting this PASS."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )
    if context.geofences:
        unbounded = [
            zone.id
            for zone in context.geofences
            if zone.floor_m is None and zone.ceiling_m is None
        ]
        if unbounded:
            context.warnings.append(
                EstimatorWarning(
                    code=WarningCode.GEOFENCE_EVALUATED_2D_ONLY,
                    message=(
                        "Geofence feasibility uses 2D lon/lat horizontal "
                        f"geometry for {len(unbounded)} zone(s) declaring "
                        "neither floor_m nor ceiling_m "
                        f"({', '.join(unbounded[:5])}). Zones declaring either "
                        "bound are additionally constrained by altitude."
                    ),
                    leg_index=None,
                    route_item_index=None,
                    route_item_id=None,
                )
            )
    geofence_evaluation = evaluate_geofence_feasibility(context)
    _raise_feasibility_failure(
        geofence_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
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
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
    )

    _warn_for_vacuous_obstacle_evidence(context)
    obstacle_evaluation = evaluate_obstacle_clearance(context)
    _raise_feasibility_failure(
        obstacle_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
        obstacle=obstacle_evaluation.obstacle,
    )

    weather_evaluation = evaluate_weather_feasibility(context)
    _raise_feasibility_failure(
        weather_evaluation.failure,
        context,
        energy=energy_evaluation.energy,
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
        obstacle=obstacle_evaluation.obstacle,
        weather=weather_evaluation.weather,
    )
    _check_failsafe_thresholds(context, energy_evaluation.energy)

    result = MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=totals.horizontal_distance_m,
        total_vertical_distance_m=totals.vertical_distance_m,
        total_path_distance_m=totals.path_distance_m,
        total_time_s=totals.time_s,
        totals_are_partial=False,
        legs=context.route_legs,
        energy=energy_evaluation.energy,
        rth_is_feasible=_rth_is_feasible(
            energy_evaluation.energy,
            resource_evaluation.resource,
            vehicle=context.vehicle,
            route_legs=context.route_legs,
        ),
        resource=resource_evaluation.resource,
        link=link_evaluation.link,
        geofence=geofence_evaluation.geofence,
        landing_zone=landing_zone_evaluation.landing_zone,
        obstacle=obstacle_evaluation.obstacle,
        weather=weather_evaluation.weather,
        ground_risk=None,
        warnings=list(context.warnings),
        failure=None,
        metadata=context.metadata,
    )
    ground_risk, ground_risk_warnings = compute_ground_risk(
        result,
        population_provider=context.population_provider,
        characteristic_dimension_m=context.vehicle.characteristic_dimension_m,
        max_speed_mps=context.vehicle.performance.max_speed_mps,
        aircraft_mass_kg=(
            context.vehicle.mass.operating_mass_kg
            if context.vehicle.mass.operating_mass_kg is not None
            else context.vehicle.mass.max_takeoff_kg
        ),
        geod=context.geod,
        max_segment_length_m=context.resolved_options.max_segment_length_m,
        population_assessment_buffer_m=(
            context.mission.sora.ground_risk_footprint.total_buffer_m
            if context.mission.sora is not None
            and context.mission.sora.ground_risk_footprint is not None
            else 0.0
        ),
    )
    context.warnings.extend(ground_risk_warnings)
    return result.model_copy(
        update={"ground_risk": ground_risk, "warnings": context.warnings}
    )


def _warn_for_vacuous_obstacle_evidence(context: EstimationContext) -> None:
    """Refuse to let an empty or zero-width obstacle check read as proven-clear.

    An obstacle provider that yields nothing, or obstacles whose whole keep-out
    volume is zero wide, produces `is_feasible=True` and satisfies the
    checklist's obstacle-evidence gate while proving nothing about masts, towers
    or power lines on the route.
    """

    provider = context.obstacle_provider
    if provider is None:
        # A terrain-clearance constraint alone still builds an obstacle estimate,
        # so the gate is satisfied with checked_obstacle_count == 0. Declaring a
        # clearance minimum and consulting no obstacle database at all is a
        # weaker claim than an empty file, not a stronger one.
        if context.mission.constraints.min_obstacle_clearance_m is not None:
            context.warnings.append(
                EstimatorWarning(
                    code=WarningCode.OBSTACLE_ZERO_FEATURES,
                    message=(
                        "constraints.min_obstacle_clearance_m is set but no "
                        "obstacle source is configured, so the clearance check "
                        "evaluated no vertical structure. Set "
                        "assets.obstacles_file before trusting this PASS."
                    ),
                    leg_index=None,
                    route_item_index=None,
                    route_item_id=None,
                )
            )
        return
    obstacles = list(provider.obstacles())
    if not obstacles:
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.OBSTACLE_ZERO_FEATURES,
                message=(
                    "An obstacle file is configured but contains zero obstacles; "
                    "the clearance check evaluated no vertical structure. Verify "
                    "the fetch produced real coverage before trusting this PASS."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )
        return
    clearance_m = context.mission.constraints.min_obstacle_clearance_m or 0.0
    if clearance_m > 0.0:
        return
    if all(
        (obstacle.radius_m + obstacle.uncertainty_m) <= 0.0 for obstacle in obstacles
    ):
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.OBSTACLE_KEEP_OUT_NOT_CONFIGURED,
                message=(
                    "Every obstacle has zero radius and zero uncertainty and "
                    "constraints.min_obstacle_clearance_m is unset, so the "
                    "keep-out volume has no width and only an exact overflight "
                    "could be detected. Set min_obstacle_clearance_m."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )


def _check_energy_model_calibration(context: EstimationContext) -> None:
    """Warn when the vehicle's power coefficients have no stated provenance."""
    status = context.vehicle.calibration_status
    if status in _CALIBRATED_STATUSES:
        return
    declared = str(status) if status is not None else "not declared"
    context.warnings.append(
        EstimatorWarning(
            code=WarningCode.ENERGY_MODEL_UNCALIBRATED,
            message=(
                f"vehicle.calibration_status is {declared}, so every energy "
                "figure below rests on unvalidated coefficients. Fit a "
                "calibration profile from a real flight trace "
                "(bvlos-sim calibrate) and pass it with --calibration, or set "
                "calibration_status to manufacturer_derived once the values "
                "come from published data."
            ),
            leg_index=None,
            route_item_index=None,
            route_item_id=None,
        )
    )


def _check_max_wind(context: EstimationContext) -> None:
    """Emit a warning for each leg where measured wind exceeds vehicle max_wind_mps."""
    max_wind = context.vehicle.performance.max_wind_mps
    if max_wind is None:
        return
    for leg in context.route_legs:
        if leg.wind_speed_mps is not None and leg.wind_speed_mps > max_wind:
            context.warnings.append(
                EstimatorWarning(
                    code=WarningCode.MAX_WIND_EXCEEDED,
                    message=(
                        f"Wind speed {leg.wind_speed_mps:.1f} m/s exceeds "
                        f"vehicle.performance.max_wind_mps ({max_wind:.1f} m/s). "
                        "The estimator does not enforce this limit; review feasibility."
                    ),
                    leg_index=leg.leg_index,
                    route_item_index=leg.route_item_index,
                    route_item_id=leg.route_item_id,
                )
            )


def _check_failsafe_thresholds(
    context: EstimationContext,
    energy: EnergyEstimate | None,
) -> None:
    """Emit warnings when predicted reserve at landing violates failsafe thresholds."""
    if energy is None or context.vehicle.failsafe is None:
        return
    reserve_pct = energy.reserve_at_landing_percent
    failsafe = context.vehicle.failsafe
    if (
        failsafe.low_battery_abort_percent is not None
        and reserve_pct < failsafe.low_battery_abort_percent
    ):
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD,
                message=(
                    f"Predicted reserve at landing ({reserve_pct:.1f}%) is below "
                    f"vehicle failsafe abort threshold "
                    f"({failsafe.low_battery_abort_percent:.1f}%). "
                    "The autopilot may trigger an emergency landing before completing the route."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )
    elif (
        failsafe.low_battery_warn_percent is not None
        and reserve_pct < failsafe.low_battery_warn_percent
    ):
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD,
                message=(
                    f"Predicted reserve at landing ({reserve_pct:.1f}%) is below "
                    f"vehicle failsafe low-battery warning threshold "
                    f"({failsafe.low_battery_warn_percent:.1f}%)."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )


def _check_route_structure(context: EstimationContext) -> None:
    """Warn when route items appear after RTL, which produces misleading results."""
    from bvlos_sim.schemas.mission import MissionAction  # local to avoid circular at module load

    rtl_index: int | None = None
    for i, item in enumerate(context.mission.route):
        if item.action == MissionAction.RTL:
            rtl_index = i
            break
    if rtl_index is not None and rtl_index < len(context.mission.route) - 1:
        trailing = [
            item.action.value for item in context.mission.route[rtl_index + 1 :]
        ]
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.ROUTE_ACTIONS_AFTER_RTL,
                message=(
                    f"RTL appears at route index {rtl_index} but is not the last item. "
                    f"Actions after RTL ({trailing}) are estimated but operationally unreachable."
                ),
                leg_index=None,
                route_item_index=rtl_index,
                route_item_id=context.mission.route[rtl_index].id,
            )
        )


def estimate_mission_distance_time(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    options: EstimationOptions | None = None,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    population_provider: GridPopulationProvider | None = None,
    obstacle_provider: ObstacleProvider | None = None,
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
        population_provider=population_provider,
        obstacle_provider=obstacle_provider,
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
    population_provider: GridPopulationProvider | None = None,
    obstacle_provider: ObstacleProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
    lz_unavailability: list[frozenset[str]] | None = None,
) -> MissionEstimate:
    """Run the estimator and return a result without raising on infeasibility.

    Unlike ``estimate_mission_distance_time``, this function catches
    ``EstimatorError`` and converts it into a ``MissionEstimate`` with
    ``status=INFEASIBLE`` or ``status=ERROR`` and partial leg data.
    Callers must inspect ``result.status`` before using the result — a
    returned estimate is not guaranteed to represent a feasible mission.
    """
    try:
        return estimate_mission_distance_time(
            mission,
            vehicle,
            options=options,
            wind_provider=wind_provider,
            terrain_provider=terrain_provider,
            population_provider=population_provider,
            obstacle_provider=obstacle_provider,
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
            rth_is_feasible=_rth_is_feasible(
                exc.energy,
                exc.resource,
                vehicle=vehicle,
                route_legs=exc.partial_legs,
            ),
            resource=exc.resource,
            link=exc.link,
            geofence=exc.geofence,
            landing_zone=exc.landing_zone,
            obstacle=exc.obstacle,
            weather=exc.weather,
            ground_risk=None,
            warnings=exc.warnings,
            failure=exc.failure,
            metadata=exc.metadata,
        )
