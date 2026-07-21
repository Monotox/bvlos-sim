"""Fetch static obstacle candidates from Overpass and write obstacle GeoJSON.

Output schema: obstacle-geojson.v1. The estimator expects properties.height_m
to be the obstacle top altitude in metres AMSL. OSM height tags are usually AGL,
so this helper adds --base-altitude-amsl-m when no ele tag is available.
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

_MISSING_REQUESTS = (
    "'requests' package not installed; run: pip install 'bvlos-sim[scripts]'"
)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HEIGHT_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _object_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value


def _parse_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    match = _HEIGHT_RE.search(value)
    if match is None:
        return None
    return float(match.group(0))


def _height_amsl(
    tags: dict[str, object], default_height_m: float, base_altitude_amsl_m: float
) -> float:
    height_agl_m = _parse_float(tags.get("height")) or default_height_m
    ele_m = _parse_float(tags.get("ele"))
    return (ele_m if ele_m is not None else base_altitude_amsl_m) + height_agl_m


def _query_overpass(
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
) -> list[dict[str, object]]:
    if requests is None:
        raise RuntimeError(_MISSING_REQUESTS)
    bbox = f"{lat_min},{lon_min},{lat_max},{lon_max}"
    query = (
        "[out:json][timeout:60];\n"
        "(\n"
        f'  node["man_made"~"^(tower|mast|crane)$"]({bbox});\n'
        f'  way["man_made"~"^(tower|mast|crane)$"]({bbox});\n'
        f'  way["power"="line"]({bbox});\n'
        f'  way["building"]({bbox});\n'
        ");\n"
        "out body geom;\n"
    )
    headers = {"User-Agent": "bvlos-sim/fetch_obstacles"}
    response = requests.post(
        _OVERPASS_URL,
        data={"data": query},
        headers=headers,
        timeout=90,
    )
    response.raise_for_status()
    payload: object = response.json()
    return [
        _object_dict(element)
        for element in _object_list(_object_dict(payload).get("elements"))
        if isinstance(element, dict)
    ]


def _node_feature(
    element: dict[str, object],
    *,
    default_height_m: float,
    default_radius_m: float,
    default_uncertainty_m: float,
    base_altitude_amsl_m: float,
) -> dict[str, object] | None:
    lat = _parse_float(element.get("lat"))
    lon = _parse_float(element.get("lon"))
    if lat is None or lon is None:
        return None
    tags = _object_dict(element.get("tags"))
    return _feature(
        element,
        geometry={"type": "Point", "coordinates": [lon, lat]},
        tags=tags,
        default_height_m=default_height_m,
        default_radius_m=default_radius_m,
        default_uncertainty_m=default_uncertainty_m,
        base_altitude_amsl_m=base_altitude_amsl_m,
    )


def _way_feature(
    element: dict[str, object],
    *,
    default_height_m: float,
    default_radius_m: float,
    default_uncertainty_m: float,
    base_altitude_amsl_m: float,
) -> dict[str, object] | None:
    geometry = _object_list(element.get("geometry"))
    coordinates = [
        _node_coordinate(_object_dict(node))
        for node in geometry
        if isinstance(node, dict)
    ]
    coordinates = [coordinate for coordinate in coordinates if coordinate is not None]
    if len(coordinates) < 2:
        return None
    tags = _object_dict(element.get("tags"))
    geometry_type = (
        {"type": "Polygon", "coordinates": [_closed_ring(coordinates)]}
        if tags.get("building") is not None and len(coordinates) >= 3
        else {"type": "LineString", "coordinates": coordinates}
    )
    return _feature(
        element,
        geometry=geometry_type,
        tags=tags,
        default_height_m=default_height_m,
        default_radius_m=default_radius_m,
        default_uncertainty_m=default_uncertainty_m,
        base_altitude_amsl_m=base_altitude_amsl_m,
    )


def _node_coordinate(node: dict[str, object]) -> list[float] | None:
    lat = _parse_float(node.get("lat"))
    lon = _parse_float(node.get("lon"))
    if lat is None or lon is None:
        return None
    return [lon, lat]


def _closed_ring(coordinates: list[list[float]]) -> list[list[float]]:
    if coordinates[0] == coordinates[-1]:
        return coordinates
    return [*coordinates, coordinates[0]]


def _feature(
    element: dict[str, object],
    *,
    geometry: dict[str, object],
    tags: dict[str, object],
    default_height_m: float,
    default_radius_m: float,
    default_uncertainty_m: float,
    base_altitude_amsl_m: float,
) -> dict[str, object]:
    element_id = str(element.get("id", "unknown"))
    properties = {
        "height_m": _height_amsl(tags, default_height_m, base_altitude_amsl_m),
        "radius_m": default_radius_m,
        "uncertainty_m": default_uncertainty_m,
        "source": "overpass",
        "source_id": element_id,
    }
    name = tags.get("name")
    if name is not None:
        properties["name"] = str(name)
    return {
        "type": "Feature",
        "id": f"overpass-{element.get('type', 'element')}-{element_id}",
        "geometry": geometry,
        "properties": properties,
    }


def _features(
    elements: list[dict[str, object]],
    *,
    default_height_m: float,
    default_radius_m: float,
    default_uncertainty_m: float,
    base_altitude_amsl_m: float,
) -> list[dict[str, object]]:
    features: list[dict[str, object]] = []
    for element in elements:
        feature = (
            _node_feature(
                element,
                default_height_m=default_height_m,
                default_radius_m=default_radius_m,
                default_uncertainty_m=default_uncertainty_m,
                base_altitude_amsl_m=base_altitude_amsl_m,
            )
            if element.get("type") == "node"
            else _way_feature(
                element,
                default_height_m=default_height_m,
                default_radius_m=default_radius_m,
                default_uncertainty_m=default_uncertainty_m,
                base_altitude_amsl_m=base_altitude_amsl_m,
            )
        )
        if feature is not None:
            features.append(feature)
    return features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("--output", default="obstacles.geojson", metavar="PATH")
    parser.add_argument("--default-height-m", type=float, default=30.0)
    parser.add_argument("--default-radius-m", type=float, default=10.0)
    parser.add_argument("--default-uncertainty-m", type=float, default=10.0)
    parser.add_argument("--base-altitude-amsl-m", type=float, default=0.0)
    args = parser.parse_args()

    if requests is None:
        sys.exit(f"Error: {_MISSING_REQUESTS}")

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")

    print(
        f"Querying Overpass for obstacles in lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] ..."
    )
    elements = _query_overpass(
        lat_min=args.lat_min,
        lat_max=args.lat_max,
        lon_min=args.lon_min,
        lon_max=args.lon_max,
    )
    payload = {
        "type": "FeatureCollection",
        "features": _features(
            elements,
            default_height_m=args.default_height_m,
            default_radius_m=args.default_radius_m,
            default_uncertainty_m=args.default_uncertainty_m,
            base_altitude_amsl_m=args.base_altitude_amsl_m,
        ),
    }
    output = Path(args.output)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(payload['features'])} obstacle features to {output}")


if __name__ == "__main__":
    main()
