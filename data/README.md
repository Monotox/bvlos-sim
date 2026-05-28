# Data Assets

Static GeoJSON assets used by the pipeline demo missions.

| Path | Description |
|---|---|
| `geofences/demo.geojson` | One forbidden no-fly zone polygon north-east of the demo route. |
| `landing_zones/demo.geojson` | One grass landing zone point at the first waypoint. |

These files are referenced from mission YAMLs via relative paths such as:

```yaml
assets:
  geofences_file: ../../data/geofences/demo.geojson
  landing_zones_file: ../../data/landing_zones/demo.geojson
```

## Real-world assets

For real-world operations use the fetch scripts to download live data:

```bash
uv run python scripts/fetch_geofences.py --lat 52.0 --lon 4.0 --radius-km 20 --output data/geofences/my_area.geojson
uv run python scripts/fetch_landing_zones.py --lat 52.0 --lon 4.0 --radius-km 20 --output data/landing_zones/my_area.geojson
```

See `examples/real_world/` for a pre-fetched Alpine example.
