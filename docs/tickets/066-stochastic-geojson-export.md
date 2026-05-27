# Ticket 066: Stochastic Propagation GeoJSON Export

## Goal

Add `--format geojson` and `--format kml` output modes to the `propagate`
CLI command. The export renders the mean particle trajectory as a LineString
coloured by per-step reserve-violation probability, making it possible to
load the propagation result directly into QGroundControl, QGIS, or Google
Earth.

## Motivation

`propagate` already computes a per-step timeline with `lat_mean`, `lon_mean`,
and `p_reserve_violation`. All the data needed for a map layer is present; it
is locked inside a JSON envelope that requires bespoke parsing. A GeoJSON
adapter — roughly 80 lines — makes the stochastic result visible without any
new computation. A drone operations team can immediately overlay the
probability-of-reserve-violation heatmap on the planned route and spot the
flight phase where mid-flight risk peaks.

## Output Format

A single GeoJSON FeatureCollection with two named layers.

### `trajectory` layer — mean particle path

One LineString over all timeline points, plus per-point properties as a
parallel feature array (or embedded in a MultiPoint feature).

```json
{
  "type": "Feature",
  "geometry": {
    "type": "LineString",
    "coordinates": [[lon0, lat0], [lon1, lat1], ...]
  },
  "properties": {
    "layer": "trajectory",
    "propagation_id": "my-propagation",
    "feasibility_rate": 0.92,
    "sample_count": 100,
    "dt_s": 2.0
  }
}
```

### `timeline` layer — one Point per timeline step

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [lon, lat] },
  "properties": {
    "layer": "timeline",
    "elapsed_time_s": 42.0,
    "energy_remaining_wh_mean": 812.3,
    "energy_remaining_wh_p5": 740.0,
    "energy_remaining_wh_p95": 890.0,
    "p_reserve_violation": 0.04
  }
}
```

`p_reserve_violation` drives point colour: green < 0.05, amber 0.05–0.20,
red > 0.20. Standard GeoJSON renderers in QGroundControl and QGIS can apply
this styling directly.

### KML variant

KML mirrors the GeoJSON structure: one `Placemark` per timeline step as a
`Point`, plus one `Placemark` LineString for the trajectory. Colour is
encoded as AABBGGRR in the `color` element, mapped from
`p_reserve_violation`.

## Acceptance Criteria

1. `propagate --format geojson` produces valid GeoJSON that passes
   `geojson.is_valid()`.
2. The `trajectory` Feature's LineString has one coordinate pair per
   timeline point in the same order.
3. Each `timeline` Feature includes `elapsed_time_s`,
   `energy_remaining_wh_mean`, `p_reserve_violation`.
4. `propagate --format kml` produces a KML document parseable by
   standard XML parsers.
5. Output can be saved with `--output` and read by QGIS / QGC without
   modification.
6. Tests: valid GeoJSON structure, coordinate count matches timeline
   length, KML root tag present.

## Scope

- `adapters/stochastic_geojson.py` — new GeoJSON builder for stochastic results
- `adapters/stochastic_kml.py` — new KML builder for stochastic results
- `adapters/cli.py` — extend `propagate` command's format enum to include
  `geojson` and `kml`; wire new builders
- `adapters/cli_support.py` — extend `_render_stochastic_output` with
  geojson/kml branches
- `tests/test_stochastic_cli.py` — geojson and kml format tests

## Notes

- Reuse the coordinate ordering convention from `adapters/geojson_export.py`
  (lon, lat, not lat, lon) to match GeoJSON spec.
- When `sample_count == 0` (all particles infeasible), the trajectory is
  an empty LineString and the timeline layer is empty — output must still
  be valid GeoJSON.
- `estimation_error_timeline` and `cross_track_timeline` are out of scope
  for this ticket; they can be added later as separate layers.
- Priority: immediately after Ticket 063 (RTH reserve) and Ticket 064
  (batch scenario/propagate).
