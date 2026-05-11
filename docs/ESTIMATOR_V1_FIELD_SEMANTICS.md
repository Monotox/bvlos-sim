# Estimator Field Semantics

This document describes which input fields affect current estimator behavior
and which fields are accepted for compatibility but not yet consumed by runtime
logic.

The default estimator mode is fidelity v1. Fidelity v2 is opt-in and adds
turn-arc dynamics, fixed-wing circular loiter, and compatibility with
sub-segment wind sampling.

## Mission Fields Used At Runtime

Top-level mission fields:

- `vehicle_profile`: checked against `vehicle.vehicle_id`
- `planned_home`: used as the initial state and RTL target
- `defaults.cruise_speed_mps`: fallback cruise speed
- `defaults.altitude_reference`: default altitude frame for route items
- `constraints.min_landing_reserve_percent`: mission reserve override
- `constraints.min_distance_to_landing_zone_m`: maximum landing-zone distance
- `assets.geofences_file`: static geofence file loaded by the CLI
- `assets.landing_zones_file`: static landing-zone file loaded by the CLI
- `estimation`: persisted estimator settings

Route item fields:

- `route[].id`: stable provenance in reports and timeline output
- `route[].action`: route action dispatch
- `route[].lat`
- `route[].lon`
- `route[].altitude_m`
- `route[].altitude_reference`
- `route[].loiter_time_s`

Mission estimation fields:

- `estimation.wind_east_mps`
- `estimation.wind_north_mps`
- `estimation.wind_layers`
- `estimation.min_groundspeed_mps`
- `estimation.max_segment_length_m`
- `estimation.fidelity`

## Vehicle Fields Used At Runtime

Identity and class:

- `vehicle_id`
- `vehicle_class`
- `capabilities.hover`
- `capabilities.forward_flight`

Performance:

- `performance.cruise_speed_mps`
- `performance.hover_speed_mps`
- `performance.max_speed_mps`
- `performance.climb_rate_mps`
- `performance.descent_rate_mps`
- `performance.turn_radius_m`
- `performance.max_crab_angle_deg`
- `performance.max_station_keep_wind_mps`

Energy:

- `energy.battery_capacity_wh`
- `energy.reserve_percent_default`
- `energy.cruise_power_w`
- `energy.hover_power_w`
- `energy.climb_power_w`
- `energy.descent_power_w`

## Scenario Fields Used At Runtime

Scenario files are consumed by the scenario CLI and runner:

- `schema_version`
- `scenario_id`
- `mission_file`
- `vehicle_file`
- `initial_conditions`
- `events`
- `assertions`

Initial conditions:

- `initial_conditions.wind_east_mps`
- `initial_conditions.wind_north_mps`
- `initial_conditions.wind_layers`
- `initial_conditions.min_groundspeed_mps`
- `initial_conditions.max_segment_length_m`
- `initial_conditions.fidelity`
- `initial_conditions.lost_link_policy`
- `initial_conditions.lost_link_policy.loiter_s`
- `initial_conditions.lost_link_policy.action`
- `initial_conditions.lost_link_policy.divert_target_id`

Events:

- `events[].event_id`
- `events[].kind`
- `events[].trigger`
- `events[].trigger_route_item_id`
- `events[].trigger_elapsed_time_s`
- `events[].wind_east_mps`
- `events[].wind_north_mps`
- `events[].wind_layers`

Assertions:

- `assertions[].assertion_id`
- `assertions[].kind`
- `assertions[].field_path`
- `assertions[].expected`
- `assertions[].event_id`

## Accepted But Non-Operative Fields

Mission:

- `mission_id`
- `defaults.hover_speed_mps`
- `constraints.max_wind_mps`
- `assets.comms_coverage_file`
- `policy.lost_link_policy`
- `metadata`
- `route[].acceptance_radius_m`
- `route[].loiter_radius_m`
- `route[].metadata`

Vehicle:

- `display_name`
- `mav_type`
- `autopilot`
- `mass.*`
- `performance.max_wind_mps`
- `failsafe.*`
- `sitl.*`
- `metadata`

Scenario:

- `description`
- `events[].description`
- `assertions[].description`
- `metadata`

Non-operative fields are accepted for schema stability, interoperability, and
future simulator phases. They must not be treated as enforced behavior unless
this document and the implementation are updated together.

## Wind Semantics

Constant wind:

- `wind_east_mps` is positive toward east.
- `wind_north_mps` is positive toward north.
- Constant wind applies when no layered wind provider is configured.

Layered wind:

- `wind_layers` configures an altitude-banded `LayeredWindProvider`.
- Each layer defines a lower altitude bound and a constant EN wind vector.
- The highest layer not exceeding the query altitude is used.
- Queries below all configured layers use the lowest layer.
- `wind_layers` supersedes scalar wind fields.
- Scalar wind fields may coexist with `wind_layers`; they are ignored while layers are present.

Scenario wind changes:

- `wind_change` events require either `wind_east_mps` plus `wind_north_mps`, or
  a non-empty `wind_layers` list.
- Wind-change payloads are only valid on `wind_change` events.
- When a wind-change event fires, its wind provider applies from the resolved
  timeline elapsed time onward.
- Multiple wind changes are applied in event order; later events at the same
  elapsed time supersede earlier ones.
- Route-item wind-change triggers are resolved deterministically against the
  scenario timeline and re-estimated until the schedule is stable.

Runtime precedence:

- Runtime `EstimationOptions` take precedence over mission `estimation`.
- CLI `--wind-layer` provides an explicit `LayeredWindProvider`.
- Scenario `initial_conditions` override mission `estimation` for scenario runs.
- The `scenario` CLI loads mission asset wind grids when the scenario leaves
  initial wind unset. Explicit scenario scalar wind or `wind_layers` take
  precedence over the mission wind-grid asset.
- If runtime options are used while mission `wind_layers` are present and no explicit wind provider is supplied, result metadata records `mission_wind_layers_ignored=true`.

## Fidelity Semantics

Fidelity v1:

- default mode
- geodesic leg-to-leg transit
- no turn dynamics
- station-keep loiter for hover-capable vehicles
- fixed-wing `loiter_time` is unsupported

Fidelity v2:

- opt-in through Python API, CLI, mission YAML, or scenario YAML
- injects `TURN_ARC` legs at waypoint heading changes of at least 1 degree
- turn arc path distance is `turn_radius_m * abs(delta_heading_rad)`
- turn arc has zero net displacement
- fixed-wing `loiter_time` is modeled as circular loiter
- hover-capable vehicles continue to use station-keep loiter

Result metadata field `estimator_version` records the actual fidelity used:
`"v1"` or `"v2"`.

## Energy Semantics

- Energy is evaluated after route kinematics are expanded.
- Mission reserve override comes from `constraints.min_landing_reserve_percent`.
- Vehicle default reserve comes from `energy.reserve_percent_default`.
- `climb_power_w` and `descent_power_w` fall back to `cruise_power_w` when omitted.
- `hover_power_w` is required for hover-capable loiter dwell.
- Fixed-wing circular loiter in fidelity v2 uses `cruise_power_w`.
- Energy infeasibility does not make distance/time totals partial.

## Geofence Semantics

- `assets.geofences_file` is loaded by the CLI when present.
- Relative geofence paths resolve from the mission file directory.
- GeoJSON coordinates are interpreted in `[lon, lat]` order.
- Supported geometries are `Polygon` and `MultiPolygon`.
- Forbidden-zone boundary contact is a conflict.
- Required zones are evaluated as a union; route segments must be covered by that union.

## Landing-Zone Semantics

- `assets.landing_zones_file` is loaded by the CLI when present.
- Relative landing-zone paths resolve from the mission file directory.
- GeoJSON coordinates are interpreted in `[lon, lat]` order.
- Supported geometries are `Point`, `Polygon`, and `MultiPolygon`.
- Reachability is evaluated at deterministic route leg end states.
- Divert energy uses straight-line geodesic distance, resolved cruise TAS, and deterministic cruise power.
- Landing-zone v1 does not evaluate terrain, obstacles, dynamic availability, suitability scoring, weather scoring, comms dependency, or landing-zone altitude.

## Update Rule

When a non-operative field becomes operative, update all of the following in the
same change:

1. implementation
2. tests
3. this document
4. golden fixtures, if public outputs change
5. versioning policy, if contract versions change
