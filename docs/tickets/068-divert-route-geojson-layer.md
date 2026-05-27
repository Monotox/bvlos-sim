# Ticket 068: Divert Route Layer in Scenario GeoJSON/KML Export

## Goal

Add a `divert_route` layer to the `scenario --format geojson` and
`scenario --format kml` outputs when a `lost_link` event with a `divert`
action fires. The layer renders the straight-line path from the link-loss
position to the target landing zone as a visually distinct feature, making
contingency routing directly visible in QGroundControl, QGIS, or Google Earth.

## Motivation

`scenario` already computes all the data needed for a divert route layer:
`action_lat`/`action_lon` from `CommsLinkPolicyOutcome`, the target landing
zone coordinates from the loaded `LandingZone` list, and the `divert_estimate`
fields (distance, energy, reserve_after_divert, feasibility). This data
appears only in the JSON/Markdown report today. Exposing it as a GeoJSON
LineString layer gives operators an immediate map overlay for contingency
planning review — the most common use of `--format geojson` in pre-flight
workflows.

A route team loading a scenario export into QGroundControl currently sees
only the mission route and landing-zone markers. Seeing the divert path
alongside the route lets them instantly check whether the divert overflies
restricted airspace or requires altitude changes that were not modelled.

## Current Behavior

`scenario --format geojson` calls `build_geojson_export(estimate, ...)`, which
only knows about the mission route legs, landing zones, and geofences. It has
no access to `ScenarioResult.event_outcomes`, so no divert path appears.

## Implementation

### 1 — New `adapters/scenario_geojson.py`

A new `build_scenario_geojson_export(scenario_result, *, ...)` function that:

1. Calls the existing `build_geojson_export` for the base layers (route,
   landing zones, geofences).
2. Iterates `scenario_result.event_outcomes` for `lost_link` events where
   `policy_outcome.action == "divert"`.
3. For each such outcome, emits a `divert_route` LineString feature:
   - Coordinates: `[action_lon, action_lat]` → target zone `[lon, lat]`
   - Properties include: `layer: "divert_route"`, `event_id`, `target_zone_id`,
     `loiter_s`, `action_at_elapsed_s`, `distance_m`, `time_s`,
     `reserve_after_divert_wh`, `reserve_after_divert_percent`, `feasible`.
4. Emits a `divert_action_point` Point feature at `[action_lon, action_lat]`:
   - Properties include: `layer: "divert_action_point"`, `event_id`,
     `action_at_elapsed_s`, `action_altitude_amsl_m`.

Target zone coordinates are resolved by matching `target_zone_id` against the
`landing_zones` list passed in.

```python
def build_scenario_geojson_export(
    scenario_result: ScenarioResult,
    estimate: MissionEstimate,
    *,
    geofence_zones: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
) -> str: ...
```

### 2 — New `adapters/scenario_kml.py`

Analogous `build_scenario_kml_export` that delegates the base layers to
the existing `build_kml_export` and appends a `divert_route` LineString
in a separate KML `Folder` with `<Style>` distinguishing the divert path
(dashed amber line, distinct from route green/amber/red).

### 3 — Update `adapters/cli.py`

In the `scenario` command's route-export branch, use
`build_scenario_geojson_export` / `build_scenario_kml_export` instead of
the generic `build_geojson_export` / `build_kml_export`. The `ScenarioResult`
and loaded `landing_zones` list are already in scope at that call site.

### 4 — Update `adapters/cli_support.py`

The `RouteExportBuilder` protocol accepts only `(estimate, *, geofence_zones,
landing_zones)`. Introduce a `ScenarioRouteExportBuilder` protocol variant
that also accepts `scenario_result: ScenarioResult`, and wire it into the
scenario render path.

### 5 — Tests

- `tests/test_scenario_geojson.py`: unit tests for `build_scenario_geojson_export`
  covering (a) no divert events → same output as `build_geojson_export`,
  (b) single divert event → `divert_route` LineString present with correct
  coordinates and properties, (c) multiple divert events → one feature per event.
- CLI integration test: `scenario --format geojson` on
  `pipeline_demo_001_divert_routing_scenario.yaml` → output contains a feature
  with `"layer": "divert_route"`.

### 6 — Golden fixtures and documentation

- Update `docs/USAGE.md` Scenario Execution GeoJSON section to mention the
  `divert_route` layer.
- No schema version bump required: GeoJSON export is not a versioned envelope.

## Integration

Composes with Ticket 055 (GeoJSON/KML route export) as a scenario-specific
extension of `build_geojson_export`. The existing `estimate --format geojson`
path is unchanged. The `scenario --format geojson` path becomes
scenario-aware. Both still use the same base route/landing-zone/geofence
layers.

## Acceptance Criteria

- `scenario --format geojson` with a divert scenario includes a
  `divert_route` LineString feature and a `divert_action_point` Point feature.
- `scenario --format geojson` with no divert event produces identical output
  to `estimate --format geojson` for the same mission+vehicle.
- `scenario --format kml` includes the divert route in a separate KML Folder.
- All existing scenario and estimate GeoJSON/KML tests continue to pass.
