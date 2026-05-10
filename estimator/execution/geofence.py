"""Deterministic static geofence feasibility evaluation."""

from dataclasses import dataclass

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import explain_validity

from estimator.core.enums import FailureCode, FailureKind, GeofenceKind
from estimator.core.geofence import GeofenceZone
from estimator.core.results import (
    EstimatorContextValue,
    EstimatorFailure,
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

    forbidden_zones = [
        zone for zone in compiled_zones if zone.zone.kind == GeofenceKind.FORBIDDEN
    ]
    required_zones = [
        zone for zone in compiled_zones if zone.zone.kind == GeofenceKind.REQUIRED
    ]
    required_union = _required_union(required_zones)

    conflicts: list[GeofenceConflict] = []
    for leg in context.route_legs:
        leg_geometry = _leg_geometry(leg)
        conflicts.extend(
            _forbidden_conflicts(
                forbidden_zones=forbidden_zones,
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


def _compile_zone(zone: GeofenceZone) -> tuple[CompiledGeofence, EstimatorFailure | None]:
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
