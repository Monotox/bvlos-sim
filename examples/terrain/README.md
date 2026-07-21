# Example Terrain Grids

Offline SRTM-format elevation grids for use with `assets.terrain_file` in mission YAMLs.

| File | Coverage | Description |
|---|---|---|
| `flat_polder.yaml` | 51.99–52.01°N, 3.99–4.01°E | Uniform 10 m AMSL flat terrain for the pipeline demo area. |

## Format

```yaml
origin_lat: 51.990
origin_lon: 3.990
step_lat_deg: 0.001
step_lon_deg: 0.001
elevations_m:
  - [10.0, 10.0, ...]   # one row per latitude step, south to north
```

## Real-world terrain

Use `scripts/fetch_terrain.py` to download SRTM tiles for any bounding box:

```bash
uv sync --extra scripts   # installs srtm.py (once)

uv run python scripts/fetch_terrain.py 51.9 52.1 3.9 4.1 0.001 \
  --output examples/terrain/my_area.yaml
```

See `examples/real_world/` for a pre-fetched Alpine example with real SRTM data.
