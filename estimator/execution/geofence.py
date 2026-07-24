"""Deterministic static and time-windowed geofence feasibility evaluation."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from shapely.affinity import translate
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import explain_validity

from estimator.core.enums import FailureCode, FailureKind, GeofenceKind, WarningCode
from estimator.core.geofence import GeofenceRecurrence, GeofenceZone
from estimator.core.results import (
    EstimatorContextValue,
    EstimatorFailure,
    EstimatorWarning,
    GeofenceConflict,
    GeofenceEstimate,
    LegEstimate,
)
from estimator.execution.runtime import EstimationContext
from estimator.execution.spatial import polygon_set_to_shapely
from estimator.execution.spatial_sampling import (
    SpatialSample,
    SpatialSamplingError,
    route_leg_samples,
)


@dataclass(frozen=True)
class CompiledGeofence:
    zone: GeofenceZone
    geometry: BaseGeometry


@dataclass(frozen=True)
class GeofenceEvaluation:
    geofence: GeofenceEstimate | None
    failure: EstimatorFailure | None


def evaluate_geofence_feasibility(context: EstimationContext) -> GeofenceEvaluation:
    """Evaluate static geofences after kinematic route expansion is complete."""

    if context.geofences is None:
        return GeofenceEvaluation(geofence=None, failure=None)

    compiled_zones: list[CompiledGeofence] = []
    for zone in context.geofences:
        compiled, failure = _compile_zone(zone)
        if failure is not None:
            return GeofenceEvaluation(geofence=None, failure=failure)
        compiled_zones.append(compiled)

    leg_geometries, sampling_failure = _leg_geometries(context)
    if sampling_failure is not None:
        return GeofenceEvaluation(geofence=None, failure=sampling_failure)
    assert leg_geometries is not None

    lon_min, lon_max = _longitude_span(leg_geometries)
    if lon_min < -180.0 or lon_max > 180.0:
        compiled_zones = [
            CompiledGeofence(
                zone=compiled.zone,
                geometry=_wrap_aware_geometry(
                    compiled.geometry, lon_min=lon_min, lon_max=lon_max
                ),
            )
            for compiled in compiled_zones
        ]

    departure_time = _mission_departure_time(context)
    time_windowed = _has_time_windowed_zones(compiled_zones)
    if time_windowed and departure_time is None:
        _append_departure_time_missing_warning(context)

    forbidden_zones = [
        zone for zone in compiled_zones if zone.zone.kind == GeofenceKind.FORBIDDEN
    ]
    required_zones = [
        zone for zone in compiled_zones if zone.zone.kind == GeofenceKind.REQUIRED
    ]

    conflicts: list[GeofenceConflict] = []
    elapsed_start_s = 0.0
    for leg, leg_geometry in zip(context.route_legs, leg_geometries):
        elapsed_end_s = elapsed_start_s + leg.time_s
        if time_windowed:
            active_forbidden_zones = _active_zones_for_leg(
                forbidden_zones,
                departure_time=departure_time,
                elapsed_start_s=elapsed_start_s,
                elapsed_end_s=elapsed_end_s,
            )
            active_required_zones = _active_zones_for_leg(
                required_zones,
                departure_time=departure_time,
                elapsed_start_s=elapsed_start_s,
                elapsed_end_s=elapsed_end_s,
            )
            required_union = _required_union(active_required_zones)
        else:
            active_forbidden_zones = forbidden_zones
            active_required_zones = required_zones
            required_union = _required_union(required_zones)

        conflicts.extend(
            _forbidden_conflicts(
                forbidden_zones=active_forbidden_zones,
                leg=leg,
                leg_geometry=leg_geometry,
            )
        )
        required_conflict = _required_conflict(
            required_zones=active_required_zones,
            required_union=required_union,
            leg=leg,
            leg_geometry=leg_geometry,
        )
        if required_conflict is not None:
            conflicts.append(required_conflict)
        elapsed_start_s = elapsed_end_s

    geofence = GeofenceEstimate(
        is_feasible=not conflicts,
        checked_zone_count=len(compiled_zones),
        checked_leg_count=len(context.route_legs),
        conflicts=conflicts,
    )
    return GeofenceEvaluation(
        geofence=geofence,
        failure=_failure_from_conflict(conflicts[0]) if conflicts else None,
    )


def _compile_zone(
    zone: GeofenceZone,
) -> tuple[CompiledGeofence, EstimatorFailure | None]:
    geometry = polygon_set_to_shapely(zone.geometry.polygons)

    if geometry.is_empty or not geometry.is_valid:
        return (
            CompiledGeofence(zone=zone, geometry=geometry),
            _zone_geometry_failure(
                zone=zone,
                reason=explain_validity(geometry),
            ),
        )

    return CompiledGeofence(zone=zone, geometry=geometry), None


def _mission_departure_time(context: EstimationContext) -> datetime | None:
    departure_time = context.mission.departure_time
    if departure_time is None:
        return None
    return _normalise_datetime(departure_time)


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _has_time_windowed_zones(zones: list[CompiledGeofence]) -> bool:
    return any(_zone_has_time_window(zone.zone) for zone in zones)


def _zone_has_time_window(zone: GeofenceZone) -> bool:
    return (
        zone.active_from is not None
        or zone.active_until is not None
        or zone.recurrence is not None
    )


def _append_departure_time_missing_warning(context: EstimationContext) -> None:
    context.warnings.append(
        EstimatorWarning(
            code=WarningCode.DEPARTURE_TIME_MISSING,
            message=(
                "Time-windowed geofence zones are configured but "
                "mission.departure_time is not set; treating those zones as "
                "always active."
            ),
            leg_index=None,
            route_item_index=None,
            route_item_id=None,
        )
    )


def _active_zones_for_leg(
    zones: list[CompiledGeofence],
    *,
    departure_time: datetime | None,
    elapsed_start_s: float,
    elapsed_end_s: float,
) -> list[CompiledGeofence]:
    return [
        zone
        for zone in zones
        if _zone_active_for_leg(
            zone.zone,
            departure_time=departure_time,
            elapsed_start_s=elapsed_start_s,
            elapsed_end_s=elapsed_end_s,
        )
    ]


def _zone_active_for_leg(
    zone: GeofenceZone,
    *,
    departure_time: datetime | None,
    elapsed_start_s: float,
    elapsed_end_s: float,
) -> bool:
    if not _zone_has_time_window(zone):
        return True
    if departure_time is None:
        return True

    leg_start = departure_time + timedelta(seconds=elapsed_start_s)
    leg_end = departure_time + timedelta(seconds=elapsed_end_s)
    if zone.recurrence is not None:
        return _recurring_window_overlaps(zone, leg_start, leg_end)
    return _absolute_window_overlaps(zone, leg_start, leg_end)


def _absolute_window_overlaps(
    zone: GeofenceZone,
    leg_start: datetime,
    leg_end: datetime,
) -> bool:
    active_from = (
        _normalise_datetime(zone.active_from) if zone.active_from is not None else None
    )
    active_until = (
        _normalise_datetime(zone.active_until)
        if zone.active_until is not None
        else None
    )
    if active_from is not None and active_from > leg_end:
        return False
    if active_until is not None and active_until < leg_start:
        return False
    return True


def _recurring_window_overlaps(
    zone: GeofenceZone,
    leg_start: datetime,
    leg_end: datetime,
) -> bool:
    start_time = _time_of_day(zone.active_from, default=time.min)
    end_time = _time_of_day(zone.active_until, default=time.max)
    crosses_midnight = (
        zone.active_from is not None
        and zone.active_until is not None
        and end_time <= start_time
    )
    date = (leg_start - timedelta(days=1)).date()
    last_date = (leg_end + timedelta(days=1)).date()
    while date <= last_date:
        if _recurrence_allows_date(zone.recurrence, date.weekday()):
            window_start = datetime.combine(date, start_time, tzinfo=UTC)
            window_end = datetime.combine(date, end_time, tzinfo=UTC)
            if crosses_midnight:
                window_end += timedelta(days=1)
            if _intervals_overlap(window_start, window_end, leg_start, leg_end):
                return True
        date += timedelta(days=1)
    return False


def _time_of_day(value: datetime | None, *, default: time) -> time:
    if value is None:
        return default
    return _normalise_datetime(value).time()


def _recurrence_allows_date(
    recurrence: GeofenceRecurrence | None,
    weekday: int,
) -> bool:
    if recurrence == GeofenceRecurrence.WEEKDAYS:
        return weekday < 5
    return True


def _intervals_overlap(
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start <= right_end and left_end >= right_start


def _leg_geometries(
    context: EstimationContext,
) -> tuple[list[BaseGeometry] | None, EstimatorFailure | None]:
    """Build every leg's flown path as a densified, longitude-unwrapped line.

    A two-point line between the leg endpoints is a planar chord in degree
    space, not the flown path: it cuts inside the geodesic by tens of metres on
    a long leg away from the equator, and it wraps the wrong way round the globe
    across the antimeridian. Both make the check miss zones the aircraft
    actually enters. The shared sampler walks the true path - including
    materialized turn arcs - so the geofence check sees what every other spatial
    check sees.
    """

    legs = list(context.route_legs)
    if not legs:
        return [], None

    try:
        samples = route_leg_samples(
            legs,
            geod=context.geod,
            max_segment_length_m=context.resolved_options.max_segment_length_m,
        )
    except SpatialSamplingError as error:
        return None, _sampling_failure(error)

    return [
        _sampled_leg_geometry(leg, leg_samples)
        for leg, leg_samples in zip(legs, samples)
    ], None


def _sampled_leg_geometry(
    leg: LegEstimate,
    samples: list[SpatialSample],
) -> BaseGeometry:
    coordinates = _unwrapped_longitudes(
        [(sample.lon, sample.lat) for sample in samples]
    )
    if not coordinates:
        return Point(leg.start_lon, leg.start_lat)
    if len(coordinates) == 1:
        return Point(coordinates[0])
    return LineString(coordinates)


def _unwrapped_longitudes(
    coordinates: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Make a path continuous across the antimeridian.

    Longitudes are re-expressed on an unbroken axis, so a leg from 179.98 to
    -179.98 becomes 179.98 to 180.02 rather than a line spanning the globe the
    long way. Zones are lifted onto the same axis in _wrap_aware_geometry.
    """

    unwrapped: list[tuple[float, float]] = []
    previous_lon: float | None = None
    offset = 0.0
    for lon, lat in coordinates:
        if previous_lon is not None:
            delta = lon - previous_lon
            if delta > 180.0:
                offset -= 360.0
            elif delta < -180.0:
                offset += 360.0
        unwrapped.append((lon + offset, lat))
        previous_lon = lon
    return unwrapped


def _wrap_aware_geometry(
    geometry: BaseGeometry,
    *,
    lon_min: float,
    lon_max: float,
) -> BaseGeometry:
    """Repeat a zone at +/-360 deg when the route runs off the standard axis."""

    parts = [geometry]
    if lon_max > 180.0:
        parts.append(translate(geometry, xoff=360.0))
    if lon_min < -180.0:
        parts.append(translate(geometry, xoff=-360.0))
    if len(parts) == 1:
        return geometry
    return unary_union(parts)


def _longitude_span(geometries: list[BaseGeometry]) -> tuple[float, float]:
    bounds = [geometry.bounds for geometry in geometries if not geometry.is_empty]
    if not bounds:
        return 0.0, 0.0
    return (
        min(bound[0] for bound in bounds),
        max(bound[2] for bound in bounds),
    )


def _forbidden_conflicts(
    *,
    forbidden_zones: list[CompiledGeofence],
    leg: LegEstimate,
    leg_geometry: BaseGeometry,
) -> list[GeofenceConflict]:
    conflicts: list[GeofenceConflict] = []
    for zone in forbidden_zones:
        if _zone_overlaps_leg_altitude(zone.zone, leg) and zone.geometry.intersects(
            leg_geometry
        ):
            conflicts.append(
                _conflict(
                    code=FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE,
                    message="Route intersects a forbidden geofence zone.",
                    zone_id=zone.zone.id,
                    zone_kind=zone.zone.kind,
                    leg=leg,
                )
            )
    return conflicts


def _required_union(required_zones: list[CompiledGeofence]) -> BaseGeometry | None:
    if not required_zones:
        return None
    return unary_union([zone.geometry for zone in required_zones])


def _required_conflict(
    *,
    required_zones: list[CompiledGeofence],
    required_union: BaseGeometry | None,
    leg: LegEstimate,
    leg_geometry: BaseGeometry,
) -> GeofenceConflict | None:
    if required_union is None:
        return None

    if not required_union.covers(leg_geometry):
        return _conflict(
            code=FailureCode.ROUTE_EXITS_REQUIRED_ZONE,
            message="Route is not fully covered by the required geofence zone set.",
            zone_id=required_zones[0].zone.id if len(required_zones) == 1 else None,
            zone_kind=GeofenceKind.REQUIRED,
            leg=leg,
        )

    for zone in required_zones:
        if zone.geometry.intersects(leg_geometry) and not _zone_contains_leg_altitude(
            zone.zone,
            leg,
        ):
            return _conflict(
                code=FailureCode.ROUTE_EXITS_REQUIRED_ZONE,
                message=(
                    "Route altitude is not fully covered by the required "
                    "geofence zone set."
                ),
                zone_id=zone.zone.id,
                zone_kind=GeofenceKind.REQUIRED,
                leg=leg,
            )

    return None


def _leg_altitude_band(leg: LegEstimate) -> tuple[float, float]:
    low, high = sorted((leg.start_alt_amsl_m, leg.end_alt_amsl_m))
    return low, high


def _zone_overlaps_leg_altitude(zone: GeofenceZone, leg: LegEstimate) -> bool:
    leg_low, leg_high = _leg_altitude_band(leg)
    return (zone.floor_m is None or leg_high >= zone.floor_m) and (
        zone.ceiling_m is None or leg_low <= zone.ceiling_m
    )


def _zone_contains_leg_altitude(zone: GeofenceZone, leg: LegEstimate) -> bool:
    leg_low, leg_high = _leg_altitude_band(leg)
    return (zone.floor_m is None or leg_low >= zone.floor_m) and (
        zone.ceiling_m is None or leg_high <= zone.ceiling_m
    )


def _conflict(
    *,
    code: FailureCode,
    message: str,
    zone_id: str | None,
    zone_kind: GeofenceKind,
    leg: LegEstimate,
) -> GeofenceConflict:
    return GeofenceConflict(
        code=code,
        message=message,
        zone_id=zone_id,
        zone_kind=zone_kind,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
    )


def _failure_from_conflict(conflict: GeofenceConflict) -> EstimatorFailure:
    context: dict[str, EstimatorContextValue] = {
        "zone_id": conflict.zone_id,
        "zone_kind": conflict.zone_kind.value,
    }
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=conflict.code,
        message=conflict.message,
        leg_index=conflict.leg_index,
        route_item_index=conflict.route_item_index,
        route_item_id=conflict.route_item_id,
        context=context,
    )


def _sampling_failure(error: SpatialSamplingError) -> EstimatorFailure:
    """Fail closed: an unmappable route must not pass the geofence check."""

    leg = error.leg
    return EstimatorFailure(
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.INVALID_GEOMETRY,
        message=(
            f"Route geometry could not be sampled for geofence evaluation: {error}"
        ),
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
        context={"stage": "geofence_route_sampling"},
    )


def _zone_geometry_failure(*, zone: GeofenceZone, reason: str) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.INVALID_GEOMETRY,
        message="Geofence geometry is invalid.",
        context={
            "zone_id": zone.id,
            "zone_kind": zone.kind.value,
            "reason": reason,
        },
    )
