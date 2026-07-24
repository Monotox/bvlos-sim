"""Fetch airspace geofences and write a geofences.geojson for the estimator.

Primary source: OpenAIP (requires free API key, --source openaip --api-key KEY).
Fallback: Overpass API (keyless, way-based airspace only).
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from . import _overpass
except ImportError:
    import _overpass  # type: ignore[no-redef]  # executed as a script

try:  # package import
    from ._attribution import OPENSTREETMAP, print_attribution
except ImportError:  # executed as a script
    from _attribution import OPENSTREETMAP, print_attribution  # type: ignore[no-redef]

_MISSING_REQUESTS = (
    "'requests' package not installed; run: pip install 'bvlos-sim[scripts]'"
)

_OPENAIP_URL = "https://api.openaip.net/api/airspaces"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OPENAIP_FORBIDDEN_CLASSES = {"RESTRICTED", "PROHIBITED", "DANGER"}
_OVERPASS_FORBIDDEN_CLASSES = {"R", "P"}
_OVERPASS_CAUTION_CLASSES = {"C", "D"}
_SUPPORTED_GEOMETRY_TYPES = {"Polygon", "MultiPolygon"}
_TIME_WINDOW_SOURCE_KEYS = {
    "active_from": ("active_from", "activeFrom", "valid_from", "validFrom"),
    "active_until": ("active_until", "activeUntil", "valid_until", "validUntil"),
    "recurrence": ("recurrence",),
}
_SUPPORTED_RECURRENCES = {"daily", "weekdays"}


def _object_dict(value: object) -> dict[str, object]:
    """Return a string-keyed dict when value is object-like."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _object_list(value: object) -> list[object]:
    """Return value when it is a list."""
    if not isinstance(value, list):
        return []
    return value


def _time_window_properties(source: dict[str, object]) -> dict[str, str]:
    """Return estimator time-window properties copied from source metadata."""
    properties: dict[str, str] = {}
    for target_key, source_keys in _TIME_WINDOW_SOURCE_KEYS.items():
        raw_value = next(
            (source[key] for key in source_keys if key in source),
            None,
        )
        if raw_value is None:
            continue
        value = str(raw_value)
        if target_key == "recurrence":
            value = value.lower()
            if value not in _SUPPORTED_RECURRENCES:
                continue
        properties[target_key] = value
    return properties


def _openaip_features(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    api_key: str,
) -> list[dict[str, object]]:
    """Call OpenAIP API and return a list of GeoJSON Feature dicts."""
    if requests is None:
        raise RuntimeError(_MISSING_REQUESTS)
    params = {"bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}"}
    headers = {"x-openaip-api-key": api_key}
    resp = requests.get(_OPENAIP_URL, params=params, headers=headers, timeout=60)
    resp.raise_for_status()
    payload: object = resp.json()
    features = _object_list(_object_dict(payload).get("features"))
    return [
        feature
        for raw_feature in features
        if (feature := _openaip_feature(_object_dict(raw_feature))) is not None
    ]


def _openaip_feature(feature: dict[str, object]) -> dict[str, object] | None:
    """Convert a single OpenAIP feature to estimator geofence GeoJSON."""
    geometry = _object_dict(feature.get("geometry"))
    geometry_type = geometry.get("type")
    if geometry_type not in _SUPPORTED_GEOMETRY_TYPES:
        return None

    properties = _object_dict(feature.get("properties"))
    name_value = properties.get("name")
    name = "Unknown" if name_value is None else str(name_value)
    output_properties = {"kind": _openaip_kind(properties), "name": name}
    output_properties.update(_time_window_properties(properties))
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": output_properties,
    }


def _overpass_elements(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
) -> list[dict[str, object]]:
    """Call Overpass API and return raw element list."""
    if requests is None:
        raise RuntimeError(_MISSING_REQUESTS)
    bbox = f"{lat_min},{lon_min},{lat_max},{lon_max}"
    query = (
        "[out:json];\n"
        "(\n"
        f'  way["boundary"="aeronautical"]["icao:class"~"^(C|D|R|P)$"]({bbox});\n'
        ");\n"
        "out geom;\n"
    )
    headers = {"User-Agent": "bvlos-sim/fetch_geofences (github.com/Monotox/bvlos-sim)"}
    resp = _overpass.post_with_retry(
        _OVERPASS_URL, data={"data": query}, headers=headers, timeout=60
    )
    payload: object = resp.json()
    elements = _object_list(_object_dict(payload).get("elements"))
    return [_object_dict(element) for element in elements if isinstance(element, dict)]


def _way_to_feature(element: dict[str, object]) -> dict[str, object] | None:
    """Convert a single Overpass way element to a GeoJSON Feature or None."""
    if element.get("type") != "way":
        return None

    geometry = _object_list(element.get("geometry"))
    coordinates = [_node_coordinate(node) for node in geometry]
    non_null: list[list[float]] = [c for c in coordinates if c is not None]
    if len(non_null) < 3:
        return None

    ring = non_null
    if ring[0] != ring[-1]:
        ring.append(ring[0])

    tags = _object_dict(element.get("tags"))
    properties = {"kind": _overpass_kind(tags), "name": _overpass_name(tags)}
    properties.update(_time_window_properties(tags))
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": properties,
    }


def _node_coordinate(node: object) -> list[float] | None:
    """Convert an Overpass geometry node to a lon-lat coordinate."""
    node_dict = _object_dict(node)
    lat = node_dict.get("lat")
    lon = node_dict.get("lon")
    if not isinstance(lat, int | float) or isinstance(lat, bool):
        return None
    if not isinstance(lon, int | float) or isinstance(lon, bool):
        return None
    return [float(lon), float(lat)]


def _openaip_kind(properties: dict[str, object]) -> str:
    """Map OpenAIP properties to geofence kind string."""
    raw_class = properties.get("icaoClass")
    if raw_class is None:
        raw_class = properties.get("type")
    class_name = "" if raw_class is None else str(raw_class).upper()
    if class_name in _OPENAIP_FORBIDDEN_CLASSES:
        return "forbidden"
    return "caution"


def _overpass_kind(tags: dict[str, object]) -> str:
    """Map Overpass icao:class tag to geofence kind string."""
    raw_class = tags.get("icao:class")
    class_name = "" if raw_class is None else str(raw_class).upper()
    if class_name in _OVERPASS_FORBIDDEN_CLASSES:
        return "forbidden"
    if class_name in _OVERPASS_CAUTION_CLASSES:
        return "caution"
    return "caution"


def _overpass_name(tags: dict[str, object]) -> str:
    """Return Overpass display name for a geofence."""
    name = tags.get("name")
    if name is not None:
        return str(name)
    class_name = tags.get("icao:class")
    if class_name is not None:
        return str(class_name)
    return "Unknown"


def _empty_features_error(source: str) -> str:
    """Return the refusal message for a fetch that produced zero features."""
    message = (
        "Error: no geofence features found; refusing to write an empty "
        "airspace file. "
    )
    if source == "overpass":
        message += (
            "Overpass returns way-based airspace only and skips relation-based "
            "zones (most CTR/TMA); retry with --source openaip for complete "
            "coverage, or pass "
        )
    else:
        message += "Pass "
    return message + "--allow-empty if the area genuinely has no airspace."



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("--source", choices=["openaip", "overpass"], default="overpass")
    parser.add_argument("--api-key", default=None, metavar="KEY")
    parser.add_argument("--output", default="geofences.geojson", metavar="PATH")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Write the output file even when zero geofence features are found",
    )
    args = parser.parse_args()

    if requests is None:
        sys.exit(f"Error: {_MISSING_REQUESTS}")

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")
    if args.source == "openaip" and (args.api_key is None or args.api_key == ""):
        sys.exit("Error: --api-key is required when --source=openaip")

    if args.source == "openaip":
        print(
            f"Querying OpenAIP for airspace geofences in "
            f"lat [{args.lat_min}, {args.lat_max}] "
            f"lon [{args.lon_min}, {args.lon_max}] …"
        )
        features = _openaip_features(
            args.lat_min, args.lat_max, args.lon_min, args.lon_max, args.api_key
        )
    else:
        print(
            f"Querying Overpass for airspace geofences in "
            f"lat [{args.lat_min}, {args.lat_max}] "
            f"lon [{args.lon_min}, {args.lon_max}] …"
        )
        try:
            elements = _overpass_elements(
                args.lat_min, args.lat_max, args.lon_min, args.lon_max
            )
        except _overpass.OverpassError as exc:
            sys.exit(f"Error: {exc}")
        print(
            "Warning: Overpass path returns way-based airspace only; "
            "relation-based zones (most CTR/TMA) are skipped. "
            "Use --source openaip for complete coverage.",
            file=sys.stderr,
        )
        features = [
            feature
            for element in elements
            if (feature := _way_to_feature(element)) is not None
        ]

    if not features and not args.allow_empty:
        sys.exit(_empty_features_error(args.source))

    geojson = {"type": "FeatureCollection", "features": features}

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(features)} features)")
    print_attribution(OPENSTREETMAP)


if __name__ == "__main__":
    main()
