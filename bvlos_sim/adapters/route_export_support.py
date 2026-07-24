"""Shared helpers for route export adapters."""

from __future__ import annotations

from typing import TypeAlias

from bvlos_sim.estimator.core.landing_zone import LandingZone, LandingZoneCoordinate
from bvlos_sim.estimator.core.results import EnergyEstimate, MissionEstimate

Coordinate2D: TypeAlias = tuple[float, float]


def energy_margin_pct(energy: EnergyEstimate | None) -> float | None:
    if energy is None:
        return None
    if energy.battery_capacity_wh == 0.0:
        return None
    reserve_margin_wh = energy.reserve_at_landing_wh - energy.reserve_threshold_wh
    return reserve_margin_wh / energy.battery_capacity_wh * 100.0


def rth_margin_pct_by_leg(energy: EnergyEstimate | None) -> dict[int, float]:
    if energy is None or energy.rth_reserve_timeline is None:
        return {}
    if energy.battery_capacity_wh == 0.0:
        return {}
    return {
        point.leg_index: point.reserve_margin_wh / energy.battery_capacity_wh * 100.0
        for point in energy.rth_reserve_timeline
    }


def rth_margin_wh_by_leg(energy: EnergyEstimate | None) -> dict[int, float]:
    if energy is None or energy.rth_reserve_timeline is None:
        return {}
    return {
        point.leg_index: point.reserve_margin_wh
        for point in energy.rth_reserve_timeline
    }


def route_margin_color(margin_pct: float | None) -> str:
    if margin_pct is None:
        return "red"
    if margin_pct > 30.0:
        return "green"
    if margin_pct >= 10.0:
        return "yellow"
    return "red"


def reachable_zone_ids(estimate: MissionEstimate) -> frozenset[str]:
    if estimate.landing_zone is None:
        return frozenset()
    return frozenset(
        state.reachable_zone_id
        for state in estimate.landing_zone.states
        if state.reachable_zone_id is not None
    )


def conflict_zone_ids(estimate: MissionEstimate) -> frozenset[str]:
    if estimate.geofence is None:
        return frozenset()
    return frozenset(
        conflict.zone_id
        for conflict in estimate.geofence.conflicts
        if conflict.zone_id is not None
    )


def landing_zone_point(zone: LandingZone) -> Coordinate2D | None:
    point = _first_landing_zone_point(zone)
    if point is not None:
        return point.lon, point.lat
    return _first_polygon_centroid(zone)


def _first_landing_zone_point(zone: LandingZone) -> LandingZoneCoordinate | None:
    return next(iter(zone.geometry.points), None)


def _first_polygon_centroid(zone: LandingZone) -> Coordinate2D | None:
    polygon = next(iter(zone.geometry.polygons), None)
    if polygon is None:
        return None
    exterior = polygon.exterior
    mean_lon = sum(coordinate.lon for coordinate in exterior) / len(exterior)
    mean_lat = sum(coordinate.lat for coordinate in exterior) / len(exterior)
    return mean_lon, mean_lat


__all__ = [
    "Coordinate2D",
    "conflict_zone_ids",
    "energy_margin_pct",
    "landing_zone_point",
    "reachable_zone_ids",
    "route_margin_color",
    "rth_margin_pct_by_leg",
    "rth_margin_wh_by_leg",
]
