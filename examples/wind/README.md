# Example Wind Grids

Spatiotemporal wind grids for use with `assets.wind_grid_file` in mission YAMLs.

| File | Coverage | Description |
|---|---|---|
| `pipeline_wind_grid.yaml` | 3×3 lat/lon, 2 alt bands, 2 time snapshots | Light easterly wind for the pipeline demo area. |

## Format (`wind-grid.v1`)

```yaml
axes:
  time_s: [0.0, 600.0]        # time snapshots in seconds from departure
  altitude_m: [0.0, 200.0]    # altitude bands in metres AMSL
  lat: [51.99, 52.00, 52.01]
  lon: [3.99, 4.00, 4.01]
values:                        # [time][alt][lat][lon] = [east_mps, north_mps]
  - - - - [2.0, 0.0]
      ...
```

Values are quadrilinearly interpolated in time, altitude, latitude, and longitude.

## Real-world wind

Use `scripts/fetch_wind.py` to download an Open-Meteo forecast:

```bash
uv run python scripts/fetch_wind.py \
  --lat 52.0 --lon 4.0 \
  --output examples/wind/forecast.yaml
```

See `examples/real_world/` for a pre-fetched Alpine example with real forecast data.
