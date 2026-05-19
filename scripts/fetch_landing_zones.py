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


def _query(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> list[dict]:
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
    return resp.json().get("elements", [])


def _to_feature(element: dict) -> dict | None:
    lat = element.get("lat") or element.get("center", {}).get("lat")
    lon = element.get("lon") or element.get("center", {}).get("lon")
    if lat is None or lon is None:
        return None
    tags = element.get("tags", {})
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
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

    print(
        f"Querying Overpass for aeroway landing zones in "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] …"
    )

    elements = _query(args.lat_min, args.lat_max, args.lon_min, args.lon_max)
    features = [f for e in elements if (f := _to_feature(e)) is not None]

    geojson = {"type": "FeatureCollection", "features": features}

    out = Path(args.output)
    out.write_text(json.dumps(geojson, indent=2))
    print(f"Wrote {out} ({len(features)} features)")


if __name__ == "__main__":
    main()
