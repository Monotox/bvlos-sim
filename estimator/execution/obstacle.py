"""Deterministic obstacle and terrain clearance evaluation."""

from dataclasses import dataclass

from pyproj import Geod
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.validation import explain_validity

from estimator.core.enums import FailureCode, FailureKind
from estimator.core.obstacle import Obstacle, ObstacleGeometryType
from estimator.core.results import (
    EstimatorContextValue,
    EstimatorFailure,
    LegEstimate,
    ObstacleClearanceViolation,
    ObstacleEstimate,
)
from estimator.environment.terrain import TerrainProvider
from estimator.execution.runtime import EstimationContext
from estimator.execution.transit import sub_segment_midpoint_fractions


@dataclass(frozen=True)
class CompiledObstacle:
    obstacle: Obstacle
    geometry: BaseGeometry


@dataclass(frozen=True)
class ObstacleEvaluation:
    obstacle: ObstacleEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class LegSample:
    leg: LegEstimate
    lat: float
    lon: float
    altitude_amsl_m: float


def evaluate_obstacle_clearance(context: EstimationContext) -> ObstacleEvaluation:
    """Evaluate static obstacle and along-leg terrain clearance."""

    obstacle_provider = context.obstacle_provider
    min_obstacle_clearance_m = context.mission.constraints.min_obstacle_clearance_m
    min_terrain_clearance_m = context.mission.constraints.min_terrain_clearance_m
    terrain_provider = context.terrain_provider
    terrain_active = min_terrain_clearance_m is not None and terrain_provider is not None
    if obstacle_provider is None and not terrain_active:
        return ObstacleEvaluation(obstacle=None, failure=None)

    obstacles = obstacle_provider.obstacles() if obstacle_provider is not None else ()
    compiled: list[CompiledObstacle] = []
    for obstacle in obstacles:
        compiled_obstacle, failure = _compile_obstacle(obstacle)
        if failure is not None:
            return ObstacleEvaluation(obstacle=None, failure=failure)
        compiled.append(compiled_obstacle)

    violations: list[ObstacleClearanceViolation] = []
    for leg in context.route_legs:
        for sample in _leg_samples(
            leg,
            geod=context.geod,
            max_segment_length_m=context.resolved_options.max_segment_length_m,
        ):
            if terrain_active and terrain_provider is not None:
                violation = _terrain_violation(
                    sample,
                    terrain_provider=terrain_provider,
                    required_clearance_m=min_terrain_clearance_m,
                )
                if violation is not None:
                    violations.append(violation)
            violations.extend(
                _obstacle_violations(
                    sample,
                    compiled_obstacles=compiled,
                    geod=context.geod,
                    required_clearance_m=min_obstacle_clearance_m or 0.0,
                )
            )

    estimate = ObstacleEstimate(
        is_feasible=not violations,
        checked_obstacle_count=len(compiled),
        checked_leg_count=len(context.route_legs),
        min_obstacle_clearance_m=min_obstacle_clearance_m,
        min_terrain_clearance_m=min_terrain_clearance_m,
        violations=violations,
    )
    return ObstacleEvaluation(
        obstacle=estimate,
        failure=_failure_from_violation(violations[0]) if violations else None,
    )


def _compile_obstacle(
    obstacle: Obstacle,
) -> tuple[CompiledObstacle, EstimatorFailure | None]:
    geometry = _obstacle_geometry(obstacle)
    if geometry.is_empty or not geometry.is_valid:
        return (
            CompiledObstacle(obstacle=obstacle, geometry=geometry),
            EstimatorFailure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_GEOMETRY,
                message="Obstacle geometry is invalid.",
                context={
                    "obstacle_id": obstacle.id,
                    "reason": explain_validity(geometry),
                },
            ),
        )
    return CompiledObstacle(obstacle=obstacle, geometry=geometry), None


def _obstacle_geometry(obstacle: Obstacle) -> BaseGeometry:
    geometry = obstacle.geometry
    if geometry.type == ObstacleGeometryType.POINT:
        point = geometry.points[0]
        return Point(point.lon, point.lat)
    if geometry.type == ObstacleGeometryType.LINE:
        return LineString([(point.lon, point.lat) for point in geometry.points])
    if geometry.polygon is None:
        return Point()
    return Polygon(
        [(point.lon, point.lat) for point in geometry.polygon.exterior]
    )


def _leg_samples(
    leg: LegEstimate,
    *,
    geod: Geod,
    max_segment_length_m: float | None,
) -> list[LegSample]:
    fractions = sub_segment_midpoint_fractions(
        leg.horizontal_distance_m,
        max_segment_length_m,
    )
    if leg.horizontal_distance_m <= 0.0:
        return [_sample_at_fraction(leg, geod=geod, track_deg=0.0, fraction=f) for f in fractions]

    track_deg = leg.ground_track_deg
    if track_deg is None:
        track_deg, _, _ = geod.inv(
            leg.start_lon,
            leg.start_lat,
            leg.end_lon,
            leg.end_lat,
        )
    return [
        _sample_at_fraction(leg, geod=geod, track_deg=track_deg, fraction=fraction)
        for fraction in fractions
    ]


def _sample_at_fraction(
    leg: LegEstimate,
    *,
    geod: Geod,
    track_deg: float,
    fraction: float,
) -> LegSample:
    if leg.horizontal_distance_m <= 0.0:
        lat = leg.start_lat
        lon = leg.start_lon
    else:
        lon, lat, _ = geod.fwd(
            leg.start_lon,
            leg.start_lat,
            track_deg,
            leg.horizontal_distance_m * fraction,
        )
    return LegSample(
        leg=leg,
        lat=lat,
        lon=lon,
        altitude_amsl_m=leg.start_alt_amsl_m
        + (leg.end_alt_amsl_m - leg.start_alt_amsl_m) * fraction,
    )


def _terrain_violation(
    sample: LegSample,
    *,
    terrain_provider: TerrainProvider,
    required_clearance_m: float,
) -> ObstacleClearanceViolation | None:
    elevation_m = terrain_provider.elevation_at(sample.lat, sample.lon)
    if elevation_m is None:
        return None
    vertical_clearance_m = sample.altitude_amsl_m - elevation_m
    if vertical_clearance_m >= required_clearance_m:
        return None
    return ObstacleClearanceViolation(
        code=FailureCode.TERRAIN_CLEARANCE_VIOLATED,
        message="Route segment violates minimum terrain clearance.",
        leg_index=sample.leg.leg_index,
        route_item_index=sample.leg.route_item_index,
        route_item_id=sample.leg.route_item_id,
        sample_lat=sample.lat,
        sample_lon=sample.lon,
        sample_alt_amsl_m=sample.altitude_amsl_m,
        vertical_clearance_m=vertical_clearance_m,
        required_clearance_m=required_clearance_m,
        terrain_elevation_m=elevation_m,
    )


def _obstacle_violations(
    sample: LegSample,
    *,
    compiled_obstacles: list[CompiledObstacle],
    geod: Geod,
    required_clearance_m: float,
) -> list[ObstacleClearanceViolation]:
    violations: list[ObstacleClearanceViolation] = []
    point = Point(sample.lon, sample.lat)
    for compiled in compiled_obstacles:
        obstacle = compiled.obstacle
        horizontal_distance_m = _distance_to_geometry_m(
            point,
            compiled.geometry,
            geod=geod,
        )
        required_m = required_clearance_m + obstacle.uncertainty_m
        horizontal_limit_m = obstacle.radius_m + required_m
        vertical_clearance_m = sample.altitude_amsl_m - obstacle.height_m
        if (
            horizontal_distance_m <= horizontal_limit_m
            and vertical_clearance_m < required_m
        ):
            violations.append(
                ObstacleClearanceViolation(
                    code=FailureCode.OBSTACLE_CLEARANCE_VIOLATED,
                    message="Route segment violates minimum obstacle clearance.",
                    leg_index=sample.leg.leg_index,
                    route_item_index=sample.leg.route_item_index,
                    route_item_id=sample.leg.route_item_id,
                    obstacle_id=obstacle.id,
                    sample_lat=sample.lat,
                    sample_lon=sample.lon,
                    sample_alt_amsl_m=sample.altitude_amsl_m,
                    horizontal_distance_m=horizontal_distance_m,
                    vertical_clearance_m=vertical_clearance_m,
                    required_clearance_m=required_m,
                )
            )
    return violations


def _distance_to_geometry_m(
    point: Point,
    geometry: BaseGeometry,
    *,
    geod: Geod,
) -> float:
    if geometry.covers(point):
        return 0.0
    nearest_on_point, nearest_on_geometry = nearest_points(point, geometry)
    _, _, distance_m = geod.inv(
        nearest_on_point.x,
        nearest_on_point.y,
        nearest_on_geometry.x,
        nearest_on_geometry.y,
    )
    return float(abs(distance_m))


def _failure_from_violation(violation: ObstacleClearanceViolation) -> EstimatorFailure:
    context: dict[str, EstimatorContextValue] = {
        "sample_lat": violation.sample_lat,
        "sample_lon": violation.sample_lon,
        "sample_alt_amsl_m": violation.sample_alt_amsl_m,
        "vertical_clearance_m": violation.vertical_clearance_m,
        "required_clearance_m": violation.required_clearance_m,
    }
    if violation.obstacle_id is not None:
        context["obstacle_id"] = violation.obstacle_id
    if violation.horizontal_distance_m is not None:
        context["horizontal_distance_m"] = violation.horizontal_distance_m
    if violation.terrain_elevation_m is not None:
        context["terrain_elevation_m"] = violation.terrain_elevation_m
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=violation.code,
        message=violation.message,
        leg_index=violation.leg_index,
        route_item_index=violation.route_item_index,
        route_item_id=violation.route_item_id,
        context=context,
    )


__all__ = ["ObstacleEvaluation", "evaluate_obstacle_clearance"]
