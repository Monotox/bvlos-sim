"""Fetch aeroway landing zones from Overpass API and write a landing_zones.geojson."""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' package not installed. Run: uv sync")

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _query(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> list[dict[str, object]]:
    bbox = f"{lat_min},{lon_min},{lat_max},{lon_max}"
    query = (
        "[out:json];\n"
        "(\n"
        f'  node["aeroway"="helipad"]({bbox});\n'
        f'  node["aeroway"="aerodrome"]({bbox});\n'
        f'  way["aeroway"="runway"]({bbox});\n'
        ");\n"
        "out center;\n"
    )
    headers = {"User-Agent": "bvlos-sim/fetch_landing_zones (github.com/Monotox/bvlos-sim)"}
    resp = requests.post(
        _OVERPASS_URL, data={"data": query}, headers=headers, timeout=60
    )
    resp.raise_for_status()
    payload = _object_dict(resp.json())
    elements = payload.get("elements")
    if not isinstance(elements, list):
        return []
    return [_object_dict(element) for element in elements]


def _to_feature(element: dict[str, object]) -> dict[str, object] | None:
    center = _object_dict(element.get("center"))
    lat = element.get("lat")
    if lat is None:
        lat = center.get("lat")
    lon = element.get("lon")
    if lon is None:
        lon = center.get("lon")
    if not isinstance(lat, int | float) or isinstance(lat, bool):
        return None
    if not isinstance(lon, int | float) or isinstance(lon, bool):
        return None
    tags = _object_dict(element.get("tags"))
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
        "properties": {"surface": tags.get("surface", "unknown")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("--output", default="landing_zones.geojson", metavar="PATH")
    args = parser.parse_args()

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")

    print(
        f"Querying Overpass for aeroway landing zones in "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] …"
    )

    elements = _query(args.lat_min, args.lat_max, args.lon_min, args.lon_max)
    features = [f for e in elements if (f := _to_feature(e)) is not None]

    geojson = {"type": "FeatureCollection", "features": features}

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(geojson, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(features)} features)")


if __name__ == "__main__":
    main()
