"""KML route export adapter for mission estimates."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from bvlos_sim.adapters.route_export_support import (
    Coordinate2D,
    conflict_zone_ids,
    energy_margin_pct,
    landing_zone_point,
    reachable_zone_ids,
)
from bvlos_sim.estimator.core.geofence import GeofencePolygon, GeofenceZone
from bvlos_sim.estimator.core.landing_zone import LandingZone
from bvlos_sim.estimator.core.results import LegEstimate, MissionEstimate

_KML_NS = "http://www.opengis.net/kml/2.2"
_ROUTE_GREEN = "ff00b050"
_ROUTE_AMBER = "ff0080ff"
_ROUTE_RED = "ff0000ff"
_ROUTE_STYLE_COLORS = {
    "route-green": _ROUTE_GREEN,
    "route-amber": _ROUTE_AMBER,
    "route-red": _ROUTE_RED,
}


def build_kml_export(
    estimate: MissionEstimate,
    *,
    geofence_zones: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
) -> str:
    """Render a mission estimate as a three-layer KML document."""

    ET.register_namespace("", _KML_NS)
    root = ET.Element(_tag("kml"))
    document = ET.SubElement(root, _tag("Document"))
    _add_route_styles(document)
    _add_route_placemarks(document, estimate)
    _add_landing_zone_placemarks(document, estimate, landing_zones)
    _add_geofence_placemarks(document, estimate, geofence_zones)
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def _add_route_styles(document: ET.Element) -> None:
    for style_id, color in _ROUTE_STYLE_COLORS.items():
        style = ET.SubElement(document, _tag("Style"), id=style_id)
        line_style = ET.SubElement(style, _tag("LineStyle"))
        ET.SubElement(line_style, _tag("color")).text = color
        ET.SubElement(line_style, _tag("width")).text = "3"


def _add_route_placemarks(document: ET.Element, estimate: MissionEstimate) -> None:
    margin_pct = energy_margin_pct(estimate.energy)
    style_url = f"#{_route_style_id(margin_pct)}"
    for leg in estimate.legs:
        placemark = ET.SubElement(document, _tag("Placemark"))
        ET.SubElement(placemark, _tag("name")).text = _leg_name(leg)
        ET.SubElement(placemark, _tag("styleUrl")).text = style_url
        extended: dict[str, str] = {
            "layer": "route",
            "leg_index": str(leg.leg_index),
            "phase": leg.phase.name,
        }
        if leg.route_item_id is not None:
            extended["route_item_id"] = leg.route_item_id
        _add_extended_data(placemark, extended)
        line_string = ET.SubElement(placemark, _tag("LineString"))
        ET.SubElement(line_string, _tag("altitudeMode")).text = "absolute"
        ET.SubElement(line_string, _tag("coordinates")).text = " ".join(
            (
                _coordinate(leg.start_lon, leg.start_lat, leg.start_alt_amsl_m),
                _coordinate(leg.end_lon, leg.end_lat, leg.end_alt_amsl_m),
            )
        )


def _add_landing_zone_placemarks(
    document: ET.Element,
    estimate: MissionEstimate,
    landing_zones: list[LandingZone] | None,
) -> None:
    if landing_zones is None:
        return

    zone_ids = reachable_zone_ids(estimate)
    for zone in landing_zones:
        point = landing_zone_point(zone)
        if point is not None:
            _add_landing_zone_placemark(document, zone, point, zone_ids)


def _add_landing_zone_placemark(
    document: ET.Element,
    zone: LandingZone,
    point: Coordinate2D,
    reachable_zone_ids: frozenset[str],
) -> None:
    lon, lat = point
    placemark = ET.SubElement(document, _tag("Placemark"))
    ET.SubElement(placemark, _tag("name")).text = zone.id
    _add_extended_data(
        placemark,
        {
            "layer": "landing_zones",
            "reachable": str(zone.id in reachable_zone_ids).lower(),
        },
    )
    point_element = ET.SubElement(placemark, _tag("Point"))
    ET.SubElement(point_element, _tag("coordinates")).text = _coordinate(lon, lat, 0.0)


def _add_geofence_placemarks(
    document: ET.Element,
    estimate: MissionEstimate,
    geofence_zones: list[GeofenceZone] | None,
) -> None:
    if geofence_zones is None:
        return

    zone_ids = conflict_zone_ids(estimate)
    for zone in geofence_zones:
        for polygon_index, polygon in enumerate(zone.geometry.polygons):
            _add_geofence_placemark(
                document,
                zone,
                polygon,
                polygon_index=polygon_index,
                conflict_zone_ids=zone_ids,
            )


def _add_geofence_placemark(
    document: ET.Element,
    zone: GeofenceZone,
    polygon: GeofencePolygon,
    *,
    polygon_index: int,
    conflict_zone_ids: frozenset[str],
) -> None:
    placemark = ET.SubElement(document, _tag("Placemark"))
    ET.SubElement(placemark, _tag("name")).text = f"{zone.id} {polygon_index + 1}"
    _add_extended_data(
        placemark,
        {
            "layer": "geofences",
            "kind": zone.kind.value,
            "conflict": str(zone.id in conflict_zone_ids).lower(),
        },
    )
    polygon_element = ET.SubElement(placemark, _tag("Polygon"))
    outer_boundary = ET.SubElement(polygon_element, _tag("outerBoundaryIs"))
    linear_ring = ET.SubElement(outer_boundary, _tag("LinearRing"))
    ET.SubElement(linear_ring, _tag("coordinates")).text = " ".join(
        _coordinate(coordinate.lon, coordinate.lat, 0.0)
        for coordinate in polygon.exterior
    )


def _add_extended_data(placemark: ET.Element, values: dict[str, str]) -> None:
    extended_data = ET.SubElement(placemark, _tag("ExtendedData"))
    for key, value in values.items():
        data = ET.SubElement(extended_data, _tag("Data"), name=key)
        ET.SubElement(data, _tag("value")).text = value


def _route_style_id(energy_margin_pct: float | None) -> str:
    if energy_margin_pct is None:
        return "route-red"
    if energy_margin_pct > 30.0:
        return "route-green"
    if energy_margin_pct >= 10.0:
        return "route-amber"
    return "route-red"


def _leg_name(leg: LegEstimate) -> str:
    if leg.route_item_id is not None:
        return f"Leg {leg.leg_index} {leg.route_item_id} ({leg.phase.name})"
    return f"Leg {leg.leg_index} {leg.phase.name}"


def _coordinate(lon: float, lat: float, alt: float) -> str:
    return f"{lon},{lat},{alt}"


def _tag(name: str) -> str:
    return f"{{{_KML_NS}}}{name}"


__all__ = ["build_kml_export"]
