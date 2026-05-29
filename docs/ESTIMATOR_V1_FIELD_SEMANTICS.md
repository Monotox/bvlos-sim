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
- `departure_time`: UTC departure timestamp used to evaluate time-windowed geofences
- `planned_home`: used as the initial state and RTL target
- `defaults.cruise_speed_mps`: fallback cruise speed
- `defaults.altitude_reference`: default altitude frame for route items
- `constraints.min_landing_reserve_percent`: mission reserve override
- `constraints.min_distance_to_landing_zone_m`: maximum landing-zone distance
- `assets.geofences_file`: static geofence file loaded by the CLI
- `assets.landing_zones_file`: static landing-zone file loaded by the CLI
- `assets.terrain_file`: offline elevation grid file loaded by the CLI for terrain-referenced altitude resolution
- `assets.population_grid_file`: offline population-density grid loaded by the CLI for SORA ground-risk pre-assessment
- `assets.wind_grid_file`: offline spatiotemporal wind grid file loaded by the CLI as a 4D wind provider
- `estimation`: persisted estimator settings
- `link_systems`: deterministic communication-link systems

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

Mission link-system fields:

- `link_systems[].link_id`
- `link_systems[].kind`
- `link_systems[].required`
- `link_systems[].priority`
- `link_systems[].availability`
- `link_systems[].max_range_m`

## Vehicle Fields Used At Runtime

Identity and class:

- `vehicle_id`
- `vehicle_class`
- `characteristic_dimension_m`: maximum span or rotor-tip diameter used with `assets.population_grid_file` to compute intrinsic Ground Risk Class
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

Resource systems:

- `resource_systems[].resource_id`
- `resource_systems[].kind`
- `resource_systems[].priority`
- `resource_systems[].battery_capacity_wh`
- `resource_systems[].reserve_percent`
- `resource_systems[].continuous_power_w`
- `resource_systems[].max_route_distance_m`
- `resource_systems[].max_route_time_s`
- `resource_systems[].max_tether_length_m`

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
- `initial_conditions.link_systems`
- `initial_conditions.link_systems[].link_id`
- `initial_conditions.link_systems[].kind`
- `initial_conditions.link_systems[].required`
- `initial_conditions.link_systems[].priority`
- `initial_conditions.link_systems[].availability`
- `initial_conditions.link_systems[].max_range_m`

Events:

- `events[].event_id`
- `events[].kind`
- `events[].trigger`
- `events[].trigger_route_item_id`
- `events[].trigger_elapsed_time_s`
- `events[].wind_east_mps`
- `events[].wind_north_mps`
- `events[].wind_layers`
- `events[].unavailable_zone_ids`
- `events[].policy` on `lost_link` events

Assertions:

- `assertions[].assertion_id`
- `assertions[].kind`
- `assertions[].field_path`
- `assertions[].expected`
- `assertions[].event_id`

Supported resource/link assertion field paths:

- `estimate.resource.is_feasible`
- `estimate.link.is_feasible`

## Accepted But Non-Operative Fields

Mission:

- `mission_id`
- `defaults.hover_speed_mps`
- `constraints.max_wind_mps`
- `assets.comms_coverage_file`
- `policy.lost_link_policy`
- `link_systems[].coverage_asset_ref`
- `link_systems[].metadata`
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
- `resource_systems[].delivery`
- `resource_systems[].metadata`
- `failsafe.*`
- `sitl.*` (ignored by the deterministic estimator; the `sitl` CLI may copy
  these fields into `sitl-evidence.v1` simulator metadata)
- `metadata`

Scenario:

- `description`
- `initial_conditions.link_systems[].coverage_asset_ref`
- `initial_conditions.link_systems[].metadata`
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
- turn arc path distance is `turn_radius_m * abs(delta_heading_rad)`, which is the exact Dubins solution for a same-position heading change; the arc has zero net displacement
- subtracts the tangent-point offset (`turn_radius_m * tan(|Δθ|/2)`) from `path_distance_m` of both transit legs adjacent to each turn arc; offsets are clamped to zero so no leg reports a negative path distance
- total path distance in fidelity v2 equals the sum of trimmed transit-leg distances plus all turn-arc lengths, which matches the true Dubins-path length through the waypoints
- fixed-wing `loiter_time` is modeled as circular loiter
- hover-capable vehicles continue to use station-keep loiter

Vertical legs (takeoff and landing-transit) in all fidelity modes:

- `path_distance_m` equals `vertical_distance_m` (the 3D slant path distance for a purely vertical leg with zero horizontal displacement)

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
- When `vehicle.resource_systems` is configured, `result.energy` remains the
  legacy battery-only energy view and may report `is_feasible=false` while
  `result.resource.is_feasible=true`. In that case resource feasibility, not
  legacy battery capacity, determines mission resource feasibility.

## Resource Semantics

- Resource systems are configured on `vehicle.resource_systems`.
- When `resource_systems` is omitted, the estimator preserves legacy
  battery-only behavior from `vehicle.energy` and `result.resource` is `null`.
- When `resource_systems` is present, each configured system is evaluated after
  route kinematics and phase-power demand are computed.
- The mission is resource-feasible when at least one configured resource system
  is feasible. The selected system is the feasible system with the lowest
  `priority`, then lexicographically lowest `resource_id`.
- `onboard_battery` uses `battery_capacity_wh` and `reserve_percent` when set;
  otherwise it uses the legacy `vehicle.energy` capacity and mission/vehicle
  reserve threshold.
- `external_power` uses `continuous_power_w` as an effectively continuous supply
  and enforces `max_route_distance_m`, `max_route_time_s`, and
  `max_tether_length_m` when set.
- `hybrid` uses `continuous_power_w` first and charges only residual per-leg
  power demand above that supply against the onboard battery capacity.
- `fuel`, `hydrogen`, and `other` are accepted extension points but currently
  produce an unsupported resource-feasibility diagnostic when configured.
- `max_tether_length_m` is checked against the maximum horizontal distance from
  planned home observed at route leg start and end states.
- Resource infeasibility does not make distance/time totals partial.

## Link Semantics

- Link systems are configured on `mission.link_systems`.
- Scenario `initial_conditions.link_systems` replaces `mission.link_systems`
  for that scenario run when set.
- When no link systems are configured, `result.link` is `null` and link
  feasibility does not affect the estimate.
- Link checks are deterministic and make no live network, modem, satellite, or
  coverage-service calls.
- `availability: unavailable` makes that link infeasible.
- `max_range_m` is checked against the maximum horizontal distance from planned
  home observed at route leg start and end states.
- If one or more links have `required=true`, at least one required link must be
  feasible. Optional links are reported but do not make the mission infeasible.
- The selected link is the feasible required link with the lowest `priority`,
  then lexicographically lowest `link_id`; if no required links exist, the same
  selection rule is applied to feasible optional links.
- `coverage_asset_ref` is accepted for future coverage models but is always
  ignored by the estimator.
- Link infeasibility does not make distance/time totals partial.

## Geofence Semantics

- `assets.geofences_file` is loaded by the CLI when present.
- Relative geofence paths resolve from the mission file directory.
- GeoJSON coordinates are interpreted in `[lon, lat]` order.
- Supported geometries are `Polygon` and `MultiPolygon`.
- Forbidden-zone boundary contact is a conflict.
- Required zones are evaluated as a union; route segments must be covered by that union.
- `active_from`, `active_until`, and `recurrence` are optional GeoJSON feature
  properties. When present and `mission.departure_time` is set, route legs are
  checked only when their absolute time interval overlaps the zone's active
  window. When `departure_time` is missing, time-windowed zones are treated as
  always active and emit `DEPARTURE_TIME_MISSING`.

## Landing-Zone Semantics

- `assets.landing_zones_file` is loaded by the CLI when present.
- Relative landing-zone paths resolve from the mission file directory.
- GeoJSON coordinates are interpreted in `[lon, lat]` order.
- Supported geometries are `Point`, `Polygon`, and `MultiPolygon`.
- Reachability is evaluated at deterministic route leg end states.
- Divert energy uses resolved cruise TAS and deterministic cruise power; distance uses Dubins path when entry heading and turn radius are available, otherwise straight-line geodesic.
- Landing-zone v1 does not evaluate terrain, obstacles, dynamic availability, suitability scoring, weather scoring, comms dependency, or landing-zone altitude.

## Divert Routing Semantics

Divert route estimates are computed in scenario runs when a `lost_link` event
fires and the configured `lost_link_policy.action` is `divert`.

Fields computed in `CommsLinkPolicyOutcome.divert_estimate`:

- `target_zone_id`: ID of the landing zone targeted by the divert policy.
- `distance_m`: divert path distance to the nearest point of the target zone. Uses Dubins path distance (bank-angle-constrained arc + straight) when entry heading and `vehicle.performance.turn_radius_m` are both available; otherwise straight-line geodesic distance.
- `time_s`: transit time at mission or vehicle cruise TAS (`distance_m / tas_mps`).
- `energy_wh`: deterministic cruise-power energy for the divert leg (`cruise_power_w * time_s / 3600`).
- `energy_remaining_at_action_wh`: battery energy available at the action execution point, computed as `battery_capacity_wh` minus the sum of all leg energies with `leg_index <= action_at_timeline_index - 1`.
- `reserve_after_divert_wh`: `energy_remaining_at_action_wh - energy_wh`.
- `reserve_after_divert_percent`: `reserve_after_divert_wh / battery_capacity_wh * 100`.
- `reserve_threshold_wh`: the mission reserve threshold in Wh.
- `is_feasible`: `True` when `reserve_after_divert_wh >= reserve_threshold_wh`.
- `infeasible_reason`: human-readable string when `is_feasible` is `False`.
- `warnings`: list of structured diagnostic warning codes. The retired `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` enum value remains available for backwards compatibility but is no longer emitted by divert routing.

Divert routing is informational. It does not change the overall mission
estimate status. The `divert_estimate.is_feasible` field indicates whether the
planned divert leg has sufficient energy reserve.

Dubins path distance is computed by sampling representative target geometry
boundary points, projecting each candidate into a local East-North frame
centred on the vehicle position using WGS-84 geodesic bearing and distance,
and evaluating the RS (right arc + straight) and LS (left arc + straight) path
types. The shortest sampled candidate is used. Entry heading is taken from
`ground_track_deg` of the last completed leg at the action timeline index; when
no prior leg exists (e.g. `at_mission_start` trigger with no loiter), entry
heading is unavailable and the estimate falls back to straight-line geodesic
distance. Dubins distance is never applied when
`vehicle.performance.turn_radius_m` is not set. The old planar approximation
limit warning is retired.

Divert route estimates use no wind correction, no geofence intersection, and no
terrain avoidance on the divert leg. TAS is taken from
`mission.defaults.cruise_speed_mps` if set; otherwise from
`vehicle.performance.cruise_speed_mps`.

`CommsLinkPolicyOutcome.divert_estimate` is `None` when:
- the policy action is not `divert`
- no landing zones are configured in the scenario

When the target zone is not found in the configured landing zones, or when energy
is not available, `divert_estimate` is populated with `is_feasible=False` and a
descriptive `infeasible_reason`.

## Uncertainty Plan Fields Used At Runtime

Uncertainty files are consumed by the `sample` CLI command:

- `schema_version`
- `uncertainty_id`
- `mission_file`
- `vehicle_file`
- `samples`
- `seed`
- `parameters`

Parameter distributions (each may be `null` to hold the parameter at its deterministic value):

- `parameters.wind_east_mps.kind` / `mean` / `std` / `low` / `high`
- `parameters.wind_north_mps.kind` / `mean` / `std` / `low` / `high`
- `parameters.cruise_speed_mps.kind` / `mean` / `std` / `low` / `high`
- `parameters.cruise_power_w.kind` / `mean` / `std` / `low` / `high`
- `parameters.battery_capacity_wh.kind` / `mean` / `std` / `low` / `high`

Supported distribution kinds: `normal` (requires `mean` and `std > 0`), `uniform` (requires `low < high`).

## Monte Carlo Sampling Semantics

- Wind sampling (`wind_east_mps`, `wind_north_mps`) overrides the mission wind provider with a `ConstantWindProvider` for each sample. Spatiotemporal and layered wind providers are not used in sampled runs when wind parameters are specified.
- Cruise speed sampling overrides `mission.defaults.cruise_speed_mps` for each sample.
- Cruise power sampling overrides `vehicle.energy.cruise_power_w` for each sample.
- Battery capacity sampling overrides `vehicle.energy.battery_capacity_wh` for each sample.
- Terrain, geofences, and landing zones are used unchanged across all samples.
- The baseline estimate is computed once before sampling with unmodified mission, vehicle, and wind provider.
- Sampling is deterministic for a given `seed`, `samples`, and parameter configuration.
- `feasibility_rate` is the fraction of completed samples where `energy.is_feasible` is `True`. It is `None` when no completed sample produced an energy estimate.

## Output Format Semantics

### `--format summary`

Available on `estimate` and `scenario`. Emits a single line to stdout.

Estimate summary fields (space-separated, fixed-width columns):

- `FEASIBLE` / `INFEASIBLE`: mission energy feasibility.
- `reserve <value> %`: `reserve_at_landing_wh / battery_capacity_wh * 100`, formatted to one decimal place.
- `flight <Xm Ys>`: total flight time as minutes and seconds.
- `[<INFEASIBLE_REASON>]`: present only when the mission is infeasible; the first failing feasibility code.

Scenario summary fields:

- `PASSED <n>/<total>` / `FAILED <n>/<total>`: assertion counts.
- `reserve <value> %`: same computation as estimate.
- `flight <Xm Ys>`: total flight time.
- `policy <ACTION>`: lost-link policy action (`NONE`, `RTL`, `LAND`, `LOITER`, `DIVERT`), or `NONE` when no lost-link event fired.
- `[ASSERTION: <assertion_id>]`: present only when at least one assertion has outcome `FAILED`; the first failing assertion ID.

### `--format geojson`

Available on `estimate` and `scenario`. Emits a GeoJSON FeatureCollection to stdout.

Three feature layers:

- `route`: one LineString per leg. Coordinates in `[lon, lat, altitude_m]` order (RFC 7946). Properties include `leg_id`, `action`, `energy_margin_pct`, and `energy_color` (`green` / `amber` / `red`).
- `landing_zones`: one Point per configured landing zone. Properties include `zone_id`, `reachable` (boolean), and `surface` (from GeoJSON source or `"unknown"`).
- `geofences`: one Polygon per configured geofence zone. Properties include `zone_id`, `kind` (`forbidden` / `caution`), and `conflict` (boolean).

`energy_margin_pct` is computed per leg as:
`(reserve_at_landing_wh − reserve_threshold_wh) / battery_capacity_wh × 100`.

Energy color thresholds:

- `green`: `energy_margin_pct > 30`
- `amber`: `10 ≤ energy_margin_pct ≤ 30`
- `red`: `energy_margin_pct < 10`

Geofence and landing-zone layers are omitted when the corresponding asset is not configured in the mission.

### `--format kml`

Available on `estimate` and `scenario`. Emits KML to stdout using the `http://www.opengis.net/kml/2.2` namespace.

Three placemarks per leg (one per energy color style), one Placemark per landing zone, and one Placemark per geofence polygon. Color encoding uses the same thresholds as GeoJSON: `route-green` (`#00b050`), `route-amber` (`#0080ff`), `route-red` (`#0000ff`) in KML `aabbggrr` encoding.

Opens directly in Google Earth and QGroundControl.

## Update Rule

When a non-operative field becomes operative, update all of the following in the
same change:

1. implementation
2. tests
3. this document
4. golden fixtures, if public outputs change
5. versioning policy, if contract versions change
