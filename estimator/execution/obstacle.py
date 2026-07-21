"""Deterministic obstacle and terrain clearance evaluation."""

from dataclasses import dataclass
import math

from pyproj import CRS, Geod, Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry
from shapely.validation import explain_validity

from estimator.core.enums import FailureCode, FailureKind
from estimator.core.obstacle import Obstacle, ObstacleGeometryType
from estimator.core.results import (
    EstimatorContextValue,
    EstimatorFailure,
    ObstacleClearanceViolation,
    ObstacleEstimate,
)
from estimator.execution.runtime import EstimationContext
from estimator.execution.spatial_sampling import (
    SpatialSample,
    SpatialSamplingError,
    route_leg_samples,
)


@dataclass(frozen=True)
class CompiledObstacle:
    obstacle: Obstacle
    geometry: BaseGeometry


@dataclass(frozen=True)
class ObstacleEvaluation:
    obstacle: ObstacleEstimate | None
    failure: EstimatorFailure | None


def evaluate_obstacle_clearance(context: EstimationContext) -> ObstacleEvaluation:
    """Evaluate static obstacle and along-leg terrain clearance."""

    obstacle_provider = context.obstacle_provider
    min_obstacle_clearance_m = context.mission.constraints.min_obstacle_clearance_m
    min_terrain_clearance_m = context.mission.constraints.min_terrain_clearance_m
    terrain_provider = context.terrain_provider
    terrain_active = min_terrain_clearance_m is not None
    if obstacle_provider is None and not terrain_active:
        return ObstacleEvaluation(obstacle=None, failure=None)

    if terrain_active and terrain_provider is None:
        estimate = _obstacle_estimate(
            context,
            checked_obstacle_count=0,
            violations=[],
            is_feasible=False,
        )
        return ObstacleEvaluation(
            obstacle=estimate,
            failure=EstimatorFailure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.TERRAIN_COVERAGE_MISSING,
                message=(
                    "Minimum terrain clearance is configured, but no terrain "
                    "provider is available."
                ),
            ),
        )

    if terrain_active:
        assert min_terrain_clearance_m is not None

    obstacles = obstacle_provider.obstacles() if obstacle_provider is not None else ()
    compiled: list[CompiledObstacle] = []
    for obstacle in obstacles:
        compiled_obstacle, failure = _compile_obstacle(obstacle)
        if failure is not None:
            return ObstacleEvaluation(obstacle=None, failure=failure)
        compiled.append(compiled_obstacle)

    try:
        samples_by_leg = route_leg_samples(
            context.route_legs,
            geod=context.geod,
            max_segment_length_m=context.resolved_options.max_segment_length_m,
            resolution_providers=(terrain_provider,)
            if terrain_active and terrain_provider is not None
            else (),
        )
    except SpatialSamplingError as exc:
        estimate = _obstacle_estimate(
            context,
            checked_obstacle_count=len(compiled),
            violations=[],
            is_feasible=False,
        )
        return ObstacleEvaluation(
            obstacle=estimate,
            failure=EstimatorFailure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_GEOMETRY,
                message=str(exc),
                leg_index=exc.leg.leg_index,
                route_item_index=exc.leg.route_item_index,
                route_item_id=exc.leg.route_item_id,
            ),
        )

    violations: list[ObstacleClearanceViolation] = []
    for leg_samples in samples_by_leg:
        if terrain_active and terrain_provider is not None:
            terrain_violations, missing_sample = _continuous_terrain_checks(
                leg_samples,
                terrain_provider=terrain_provider,
                required_clearance_m=min_terrain_clearance_m,
                geod=context.geod,
            )
            if missing_sample is not None:
                estimate = _obstacle_estimate(
                    context,
                    checked_obstacle_count=len(compiled),
                    violations=violations,
                    is_feasible=False,
                )
                return ObstacleEvaluation(
                    obstacle=estimate,
                    failure=_terrain_coverage_failure(missing_sample),
                )
            violations.extend(terrain_violations)
        violations.extend(
            _continuous_obstacle_violations(
                leg_samples,
                compiled_obstacles=compiled,
                required_clearance_m=min_obstacle_clearance_m or 0.0,
                geod=context.geod,
            )
        )

    estimate = _obstacle_estimate(
        context,
        checked_obstacle_count=len(compiled),
        violations=violations,
    )
    return ObstacleEvaluation(
        obstacle=estimate,
        failure=_failure_from_violation(violations[0]) if violations else None,
    )


def _continuous_terrain_checks(
    samples: list[SpatialSample],
    *,
    terrain_provider,
    required_clearance_m: float,
    geod: Geod,
) -> tuple[list[ObstacleClearanceViolation], SpatialSample | None]:
    if not samples:
        return [], None
    segments = list(zip(samples, samples[1:]))
    if not segments:
        segments = [(samples[0], samples[0])]
    conservative_maximum = getattr(
        terrain_provider,
        "conservative_max_elevation_along_segment",
        None,
    )
    if not callable(conservative_maximum):
        # Endpoint-only sampling cannot prove clearance over a custom terrain
        # surface. Fail closed unless the provider supplies a segment maximum.
        return [], samples[0]
    violations: list[ObstacleClearanceViolation] = []
    for start, end in segments:
        elevation_m = conservative_maximum(
            start.lat,
            start.lon,
            end.lat,
            end.lon,
            geod=geod,
        )
        reference_sample = (
            start if start.altitude_amsl_m <= end.altitude_amsl_m else end
        )
        if elevation_m is None or isinstance(elevation_m, bool):
            return violations, reference_sample
        try:
            elevation_value = float(elevation_m)
        except (TypeError, ValueError):
            return violations, reference_sample
        if not math.isfinite(elevation_value):
            return violations, reference_sample
        violation = _terrain_violation(
            reference_sample,
            terrain_elevation_m=elevation_value,
            required_clearance_m=required_clearance_m,
        )
        if violation is not None:
            violations.append(violation)
    return violations, None


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
    return Polygon([(point.lon, point.lat) for point in geometry.polygon.exterior])


def _terrain_violation(
    sample: SpatialSample,
    *,
    terrain_elevation_m: float,
    required_clearance_m: float,
) -> ObstacleClearanceViolation | None:
    vertical_clearance_m = sample.altitude_amsl_m - terrain_elevation_m
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
        terrain_elevation_m=terrain_elevation_m,
    )


def _continuous_obstacle_violations(
    samples: list[SpatialSample],
    *,
    compiled_obstacles: list[CompiledObstacle],
    required_clearance_m: float,
    geod: Geod,
) -> list[ObstacleClearanceViolation]:
    """Check continuous route segments against metric obstacle footprints."""

    if not samples:
        return []
    violations: list[ObstacleClearanceViolation] = []
    for compiled in compiled_obstacles:
        obstacle = compiled.obstacle
        required_m = required_clearance_m + obstacle.uncertainty_m
        horizontal_limit_m = obstacle.radius_m + required_m

        conflict: tuple[float, float, float, float] | None = None
        if len(samples) == 1:
            sample = samples[0]
            forward, _ = _local_metric_transformers(sample.lat, sample.lon)
            metric_geometry = transform_geometry(forward.transform, compiled.geometry)
            metric_point = Point(*forward.transform(sample.lon, sample.lat))
            horizontal_distance_m = metric_point.distance(metric_geometry)
            if horizontal_distance_m <= horizontal_limit_m:
                conflict = (
                    sample.lon,
                    sample.lat,
                    sample.altitude_amsl_m,
                    horizontal_distance_m,
                )
        else:
            for start, end in zip(samples, samples[1:]):
                conflict = _segment_obstacle_conflict(
                    start,
                    end,
                    compiled=compiled,
                    horizontal_limit_m=horizontal_limit_m,
                    required_vertical_clearance_m=required_m,
                    geod=geod,
                )
                if conflict is not None:
                    break
        if conflict is None:
            continue
        lon, lat, altitude_m, horizontal_distance_m = conflict
        vertical_clearance_m = altitude_m - obstacle.height_m
        if vertical_clearance_m >= required_m:
            continue
        sample = samples[0]
        violations.append(
            ObstacleClearanceViolation(
                code=FailureCode.OBSTACLE_CLEARANCE_VIOLATED,
                message="Route segment violates minimum obstacle clearance.",
                leg_index=sample.leg.leg_index,
                route_item_index=sample.leg.route_item_index,
                route_item_id=sample.leg.route_item_id,
                obstacle_id=obstacle.id,
                sample_lat=lat,
                sample_lon=lon,
                sample_alt_amsl_m=altitude_m,
                horizontal_distance_m=horizontal_distance_m,
                vertical_clearance_m=vertical_clearance_m,
                required_clearance_m=required_m,
            )
        )
    return violations


def _segment_obstacle_conflict(
    start: SpatialSample,
    end: SpatialSample,
    *,
    compiled: CompiledObstacle,
    horizontal_limit_m: float,
    required_vertical_clearance_m: float,
    geod: Geod,
) -> tuple[float, float, float, float] | None:
    """Return the lowest-altitude point inside an obstacle's buffered footprint."""

    track_deg, _, distance_m = geod.inv(
        start.lon,
        start.lat,
        end.lon,
        end.lat,
    )
    distance_m = abs(float(distance_m))
    if distance_m == 0.0:
        centre_lon, centre_lat = start.lon, start.lat
    else:
        centre_lon, centre_lat, _ = geod.fwd(
            start.lon,
            start.lat,
            track_deg,
            distance_m / 2.0,
        )
    forward, inverse = _local_metric_transformers(centre_lat, centre_lon)
    metric_route = LineString(
        [
            forward.transform(start.lon, start.lat),
            forward.transform(end.lon, end.lat),
        ]
    )
    metric_geometry = transform_geometry(forward.transform, compiled.geometry)
    footprint = (
        metric_geometry
        if horizontal_limit_m == 0.0
        else metric_geometry.buffer(horizontal_limit_m, quad_segs=128)
    )
    intersection = metric_route.intersection(footprint)
    if intersection.is_empty:
        return None

    fractions = [
        metric_route.project(Point(x, y), normalized=True)
        for x, y in _intersection_coordinates(intersection)
    ]
    if not fractions:
        return None
    # Altitude is linear between stored spatial samples, so its minimum over
    # every footprint-intersection interval occurs at one of the endpoints.
    fraction = min(
        fractions,
        key=lambda value: (
            start.altitude_amsl_m
            + value * (end.altitude_amsl_m - start.altitude_amsl_m)
        ),
    )
    altitude_m = start.altitude_amsl_m + fraction * (
        end.altitude_amsl_m - start.altitude_amsl_m
    )
    if altitude_m - compiled.obstacle.height_m >= required_vertical_clearance_m:
        return None
    metric_point = metric_route.interpolate(fraction, normalized=True)
    horizontal_distance_m = metric_point.distance(metric_geometry)
    lon, lat = inverse.transform(metric_point.x, metric_point.y)
    return float(lon), float(lat), altitude_m, horizontal_distance_m


def _local_metric_transformers(
    centre_lat: float, centre_lon: float
) -> tuple[Transformer, Transformer]:
    local_crs = CRS.from_proj4(
        "+proj=aeqd "
        f"+lat_0={centre_lat:.12f} +lon_0={centre_lon:.12f} "
        "+datum=WGS84 +units=m +no_defs"
    )
    return (
        Transformer.from_crs("EPSG:4326", local_crs, always_xy=True),
        Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True),
    )


def _intersection_coordinates(geometry: BaseGeometry) -> list[tuple[float, float]]:
    if geometry.geom_type == "Point":
        point = geometry
        return [(float(point.x), float(point.y))]  # type: ignore[attr-defined]
    if hasattr(geometry, "geoms"):
        return [
            coordinate
            for part in geometry.geoms  # type: ignore[attr-defined]
            for coordinate in _intersection_coordinates(part)
        ]
    coordinates = list(geometry.coords)  # type: ignore[attr-defined]
    if len(coordinates) <= 2:
        return [(float(lon), float(lat)) for lon, lat, *_ in coordinates]
    first = coordinates[0]
    last = coordinates[-1]
    return [(float(first[0]), float(first[1])), (float(last[0]), float(last[1]))]


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


def _terrain_coverage_failure(sample: SpatialSample) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.TERRAIN_COVERAGE_MISSING,
        message="Terrain coverage is missing at a sampled route position.",
        leg_index=sample.leg.leg_index,
        route_item_index=sample.leg.route_item_index,
        route_item_id=sample.leg.route_item_id,
        context={
            "sample_lat": sample.lat,
            "sample_lon": sample.lon,
            "sample_alt_amsl_m": sample.altitude_amsl_m,
        },
    )


def _obstacle_estimate(
    context: EstimationContext,
    *,
    checked_obstacle_count: int,
    violations: list[ObstacleClearanceViolation],
    is_feasible: bool | None = None,
) -> ObstacleEstimate:
    return ObstacleEstimate(
        is_feasible=not violations if is_feasible is None else is_feasible,
        checked_obstacle_count=checked_obstacle_count,
        checked_leg_count=len(context.route_legs),
        min_obstacle_clearance_m=context.mission.constraints.min_obstacle_clearance_m,
        min_terrain_clearance_m=context.mission.constraints.min_terrain_clearance_m,
        violations=violations,
    )


__all__ = ["ObstacleEvaluation", "evaluate_obstacle_clearance"]
