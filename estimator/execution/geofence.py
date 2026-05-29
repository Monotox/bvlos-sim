"""Deterministic static and time-windowed geofence feasibility evaluation."""

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

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
    for leg in context.route_legs:
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

        leg_geometry = _leg_geometry(leg)
        conflicts.extend(
            _forbidden_conflicts(
                forbidden_zones=active_forbidden_zones,
                leg=leg,
                leg_geometry=leg_geometry,
            )
        )
        required_conflict = _required_conflict(
            required_zones=required_zones,
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


def _leg_geometry(leg: LegEstimate) -> BaseGeometry:
    start = (leg.start_lon, leg.start_lat)
    end = (leg.end_lon, leg.end_lat)
    if start == end:
        return Point(start)
    return LineString([start, end])


def _forbidden_conflicts(
    *,
    forbidden_zones: list[CompiledGeofence],
    leg: LegEstimate,
    leg_geometry: BaseGeometry,
) -> list[GeofenceConflict]:
    conflicts: list[GeofenceConflict] = []
    for zone in forbidden_zones:
        if zone.geometry.intersects(leg_geometry):
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
    if required_union is None or required_union.covers(leg_geometry):
        return None

    return _conflict(
        code=FailureCode.ROUTE_EXITS_REQUIRED_ZONE,
        message="Route is not fully covered by the required geofence zone set.",
        zone_id=required_zones[0].zone.id if len(required_zones) == 1 else None,
        zone_kind=GeofenceKind.REQUIRED,
        leg=leg,
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
