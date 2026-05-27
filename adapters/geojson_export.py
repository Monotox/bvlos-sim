"""GeoJSON route export adapter for mission estimates."""

from __future__ import annotations

import json
from typing import TypeAlias

from adapters.canonical_json import JsonValue, canonical_json_value
from adapters.route_export_support import (
    conflict_zone_ids,
    energy_margin_pct,
    landing_zone_point,
    reachable_zone_ids,
)
from estimator.core.geofence import GeofencePolygon, GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.results import EnergyEstimate, MissionEstimate

GeoJsonFeature: TypeAlias = dict[str, JsonValue]


def build_geojson_export(
    estimate: MissionEstimate,
    *,
    geofence_zones: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
) -> str:
    """Render a mission estimate as a three-layer GeoJSON FeatureCollection."""

    features = [
        *_route_features(estimate),
        *_landing_zone_features(estimate, landing_zones),
        *_geofence_features(estimate, geofence_zones),
    ]
    feature_collection: dict[str, JsonValue] = {
        "type": "FeatureCollection",
        "features": features,
    }
    return json.dumps(canonical_json_value(feature_collection), indent=2) + "\n"


def _route_features(estimate: MissionEstimate) -> list[GeoJsonFeature]:
    energy_by_leg_index = _energy_by_leg_index(estimate.energy)
    margin_pct = energy_margin_pct(estimate.energy)
    feasible = _energy_feasible(estimate.energy)
    return [
        _feature(
            geometry={
                "type": "LineString",
                "coordinates": [
                    [leg.start_lon, leg.start_lat, leg.start_alt_amsl_m],
                    [leg.end_lon, leg.end_lat, leg.end_alt_amsl_m],
                ],
            },
            properties={
                "layer": "route",
                "phase": leg.phase.name,
                "leg_index": leg.leg_index,
                "route_item_id": leg.route_item_id,
                "path_distance_m": leg.path_distance_m,
                "energy_wh": energy_by_leg_index.get(leg.leg_index),
                "energy_margin_pct": margin_pct,
                "feasible": feasible,
            },
        )
        for leg in estimate.legs
    ]


def _landing_zone_features(
    estimate: MissionEstimate,
    landing_zones: list[LandingZone] | None,
) -> list[GeoJsonFeature]:
    if landing_zones is None:
        return []

    zone_ids = reachable_zone_ids(estimate)
    features = [_landing_zone_feature(zone, zone_ids) for zone in landing_zones]
    return [feature for feature in features if feature is not None]


def _landing_zone_feature(
    zone: LandingZone,
    reachable_zone_ids: frozenset[str],
) -> GeoJsonFeature | None:
    point = landing_zone_point(zone)
    if point is None:
        return None

    lon, lat = point
    return _feature(
        geometry={"type": "Point", "coordinates": [lon, lat]},
        properties={
            "layer": "landing_zones",
            "name": zone.id,
            "reachable": zone.id in reachable_zone_ids,
        },
    )


def _geofence_features(
    estimate: MissionEstimate,
    geofence_zones: list[GeofenceZone] | None,
) -> list[GeoJsonFeature]:
    if geofence_zones is None:
        return []

    zone_ids = conflict_zone_ids(estimate)
    return [
        _geofence_feature(zone, polygon, zone_ids)
        for zone in geofence_zones
        for polygon in zone.geometry.polygons
    ]


def _geofence_feature(
    zone: GeofenceZone,
    polygon: GeofencePolygon,
    conflict_zone_ids: frozenset[str],
) -> GeoJsonFeature:
    return _feature(
        geometry={
            "type": "Polygon",
            "coordinates": [
                [[coordinate.lon, coordinate.lat] for coordinate in polygon.exterior]
            ],
        },
        properties={
            "layer": "geofences",
            "kind": zone.kind.value,
            "name": zone.id,
            "conflict": zone.id in conflict_zone_ids,
        },
    )


def _feature(
    *,
    geometry: dict[str, JsonValue],
    properties: dict[str, JsonValue],
) -> GeoJsonFeature:
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def _energy_by_leg_index(energy: EnergyEstimate | None) -> dict[int, float]:
    if energy is None:
        return {}
    return {leg.leg_index: leg.energy_wh for leg in energy.legs}


def _energy_feasible(energy: EnergyEstimate | None) -> bool | None:
    if energy is None:
        return None
    return energy.is_feasible


__all__ = ["build_geojson_export"]
