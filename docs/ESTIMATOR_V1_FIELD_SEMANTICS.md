# Estimator Field Semantics

This document describes which input fields affect current estimator behavior
and which fields are accepted for compatibility but not yet consumed by runtime
logic.

The default estimator mode is fidelity v1. Fidelity v2 is opt-in and adds
turn-arc dynamics and fixed-wing circular loiter. Straight-leg sub-segment
sampling is an independent `max_segment_length_m` option available in either
fidelity mode.

## Mission Fields Used At Runtime

Top-level mission fields:

- `schema_version`: required in mission files and must be `mission.v7`; use
  `bvlos-sim migrate` for unversioned or `mission.v6` inputs
- `vehicle_profile`: checked against `vehicle.vehicle_id`
- `departure_time`: UTC departure timestamp used to evaluate time-windowed geofences
- `planned_home`: used as the initial state and RTL target
- `defaults.cruise_speed_mps`: fallback cruise speed
- `defaults.altitude_reference`: default altitude frame for route items
- `constraints.min_landing_reserve_percent`: mission reserve override
- `constraints.require_rth_reserve`: hard per-leg return-to-home reserve gate
- `constraints.max_wind_mps`: sustained-wind feasibility limit
- `constraints.max_crosswind_mps`: cross-track wind feasibility limit
- `constraints.max_gust_mps`: fails closed until a gust-capable provider is available
- `constraints.min_visibility_m`: fails closed until a visibility provider is available
- `constraints.max_precipitation_mm_h`: fails closed until a precipitation provider is available
- `constraints.min_distance_to_landing_zone_m`: maximum landing-zone distance
- `constraints.min_obstacle_clearance_m`: horizontal and vertical separation buffer around configured obstacles
- `constraints.min_terrain_clearance_m`: minimum sampled terrain clearance when a terrain provider is configured
- `assets.geofences_file`: static geofence file loaded by the CLI
  (`floor_m`/`ceiling_m` feature properties are operative when present)
- `assets.landing_zones_file`: static landing-zone file loaded by the CLI
- `assets.terrain_file`: offline elevation grid file loaded by the CLI for terrain-referenced altitude resolution
- `assets.population_grid_file`: offline population-density grid loaded by the CLI for SORA ground-risk pre-assessment
- `assets.obstacles_file`: static obstacle GeoJSON loaded by the CLI for vertical clearance checks
- `assets.wind_grid_file`: offline spatiotemporal wind grid file loaded by the CLI as a 4D wind provider
- `estimation`: persisted estimator settings
- `link_systems`: deterministic communication-link systems
- `airspace`: SORA 2.5 Air Risk descriptor used by the `sora` command
- `sora`: SORA 2.5 footprint evidence and ground-risk mitigation declarations

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
- `characteristic_dimension_m`: wingspan for fixed-wing, rotor blade diameter for a rotorcraft, or maximum distance between blade tips for a multicopter; used with `assets.population_grid_file` and maximum possible commanded speed to compute iGRC
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
- `performance.max_wind_mps`: emits an advisory warning that blocks operational GO in every output format

Energy:

- `energy.battery_capacity_wh`
- `energy.reserve_percent_default`
- `energy.cruise_power_w`
- `energy.hover_power_w`
- `energy.climb_power_w`
- `energy.descent_power_w`
- `energy.reference_mass_kg`
- `energy.reference_density_kgm3`
- `energy.induced_power_mass_exponent`
- `energy.usable_capacity_curve`

Mass:

- `mass.operating_mass_kg`

Failsafe thresholds:

- `failsafe.low_battery_warn_percent`
- `failsafe.low_battery_abort_percent`
- `failsafe.emergency_land_percent`

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
- `estimate.obstacle.is_feasible`

## Accepted But Non-Operative Fields

Mission:

- `mission_id`
- `defaults.hover_speed_mps`
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
- `mass.empty_kg`
- `mass.max_payload_kg`
- `mass.max_takeoff_kg`
- `resource_systems[].delivery`
- `resource_systems[].metadata`
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
- Transit, emergency-return, and landing-zone divert calculations split their
  integration exactly at known wind-change boundaries. Custom time-dependent
  providers that do not expose change times are solved with a bounded
  convergence loop and fail closed when no stable travel time exists.
- Weather checks sample every leg, including zero-horizontal-distance vertical
  legs, at the endpoints, known wind-change boundaries, and at intervals no
  longer than 60 seconds. A later wind increase during a long loiter is not
  hidden by a calm initial sample.

Runtime precedence:

- Runtime `EstimationOptions` merge with mission `estimation` field by field;
  each non-null runtime field takes precedence and omitted runtime fields inherit
  the mission value.
- CLI `--wind-layer` provides an explicit `LayeredWindProvider`.
- Scenario `initial_conditions` override mission `estimation` for scenario runs.
- The `scenario` CLI loads mission asset wind grids when the scenario leaves
  initial wind unset. Explicit scenario scalar wind or `wind_layers` take
  precedence over the mission wind-grid asset.
- Mission `wind_layers` remain active when runtime options change only fidelity,
  minimum groundspeed, or segmentation. Setting either runtime scalar wind
  component explicitly replaces the layered provider with a constant provider.

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
- replaces each feasible corner with a connected circular fillet whose entry and
  exit are tangent to the adjacent transit tracks; the arc has non-zero chord
  displacement and a sampled path geometry
- trims the adjacent transit legs to those tangent points and recomputes their
  geodesic distance, time, and wind samples
- rejects a corner with `INVALID_GEOMETRY` when the tangent offsets do not fit on
  both adjacent legs; offsets are never silently clamped
- evaluates wind and geofences along the sampled arc as well as the straight
  transit portions
- fixed-wing `loiter_time` is modeled as circular loiter
- hover-capable vehicles continue to use station-keep loiter
- hover station-keep authority and fixed-wing orbit feasibility are checked for
  the full loiter dwell. A fixed-wing orbit fails when the wind triangle has no
  solution, the worst-case orbit groundspeed is below the configured minimum,
  or the required crab angle exceeds the vehicle limit.

Setting fidelity v2 does not by itself sub-segment straight transit legs. Set
`estimation.max_segment_length_m`, scenario
`initial_conditions.max_segment_length_m`, runtime
`EstimationOptions.max_segment_length_m`, or CLI `--max-segment-length-m` when
that sampling is required. The same option applies in fidelity v1.

Vertical legs (takeoff and landing-transit) in all fidelity modes:

- `path_distance_m` equals `vertical_distance_m` (the 3D slant path distance for a purely vertical leg with zero horizontal displacement)

Result metadata field `estimator_version` records the actual fidelity used:
`"v1"` or `"v2"`.

## Energy Semantics

- Energy is evaluated after route kinematics are expanded.
- Mission reserve override comes from `constraints.min_landing_reserve_percent`.
- Vehicle default reserve comes from `energy.reserve_percent_default`.
- `climb_power_w` and `descent_power_w` fall back to `cruise_power_w` when omitted.
- A route leg with positive vertical displacement uses climb power; one with
  negative vertical displacement uses descent power, including combined
  horizontal/vertical legs.
- `hover_power_w` is required for hover-capable loiter dwell.
- Fixed-wing circular loiter in fidelity v2 uses `cruise_power_w`.
- When `mass.operating_mass_kg` and `energy.reference_mass_kg` are both set,
  hover, climb, and descent power scale by
  `(operating_mass_kg / reference_mass_kg) ^ induced_power_mass_exponent`.
  Cruise, turn-arc, fixed-wing loiter, and horizontal RTL transit use the same
  mass ratio with a milder `0.5` exponent.
- When `energy.reference_density_kgm3` is set, induced-power phases (hover,
  climb, and descent) scale by the square root of
  `reference_density_kgm3 / ISA_density(leg_midpoint_altitude_amsl_m)`.
  Cruise-like phases conservatively use the larger of that ratio and its
  inverse because a single calibrated cruise number cannot separate parasite
  and induced power. The density model is deterministic ISA troposphere logic
  and performs no live weather lookup.
- `energy.usable_capacity_curve` maps state of charge to usable-capacity
  fraction. Estimator v1 applies the full-charge usable fraction as a capacity
  derating to `result.energy.usable_energy_wh`; the reserve threshold remains
  based on nominal `battery_capacity_wh`.
- These mass, density, and SoC scalings are physically motivated closed-form
  adjustments. They are not a substitute for vehicle-specific log calibration.
- Return-to-home reserve is evaluated at each route leg endpoint against
  `mission.planned_home`. When heading and turn radius are available, distance
  follows a materialized Dubins turn-and-straight path; otherwise it is the
  direct geodesic. The path is spatially sampled and its wind-triangle time is
  integrated using the active wind provider. Energy uses that time and the same
  mass/density-adjusted cruise power as route legs. Impossible wind, crab-angle,
  minimum-groundspeed, or path-geometry cases fail closed.
- Return-to-home energy also includes the terminal climb or descent from the
  route endpoint altitude to `planned_home.altitude_amsl_m`, using the resolved
  vertical rate and climb/descent power (or its documented cruise-power
  fallback). Wind changes that occur during the return affect all subsequent
  return segments.
- `result.energy.rth_reserve_timeline[].reserve_margin_wh` is
  `energy_remaining_before_rth_wh - rth_energy_wh - reserve_threshold_wh`.
- Without explicit resource systems, `result.rth_is_feasible` is `True` only
  when every battery RTH timeline point has a non-negative reserve margin. With
  a selected onboard or hybrid resource it reflects that resource's capacity,
  reserve, and residual RTH demand. It is `true` for selected continuous
  external power after route constraints and RTH peak-power demand pass; a
  battery reserve margin is not applicable. RTH reserve gates estimate
  feasibility by default; setting `constraints.require_rth_reserve: false`
  disables that estimator gate only for explicitly non-operational engineering
  analysis.
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
  reserve threshold. Its reserve check includes the energy needed to return home
  from every route state.
- `external_power` uses `continuous_power_w` as an effectively continuous supply
  and enforces `max_route_distance_m`, `max_route_time_s`, and
  `max_tether_length_m` when set. Its power check includes the peak cruise power
  required by the RTH contingency, but it does not inherit a superseded base
  battery reserve failure.
- `hybrid` uses `continuous_power_w` first and charges only residual per-leg
  power demand above that supply against the onboard battery capacity. The same
  residual-demand calculation is applied to every RTH timeline point.
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
- `floor_m` and `ceiling_m` are optional GeoJSON feature properties in metres
  AMSL. Missing lower or upper bounds behave as unbounded in that direction.
- A forbidden zone conflicts with a leg only when the horizontal geometry
  intersects and the leg altitude band overlaps the zone altitude band.
- A required zone must cover the leg horizontally and contain the full leg
  altitude band. Boundary altitudes are included in the zone.
- When both `floor_m` and `ceiling_m` are present, `ceiling_m` must be greater
  than `floor_m`. Per-zone AGL altitude references are not modelled.
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
- `properties.altitude_amsl_m` gives the landing-surface elevation. When it is
  absent, the configured terrain provider must cover the selected landing
  point; otherwise reachability fails closed with `TERRAIN_COVERAGE_MISSING`.
- Reachability is checked at route endpoints and deterministic interior samples.
  The maximum sample spacing is 50 metres unless a smaller configured spatial
  segment length applies. The half-gap around each sample is included in the
  maximum-distance test so a long uncovered interval cannot pass merely because
  both endpoints are close to different zones.
- Divert distance follows a materialized Dubins turn-and-straight path when
  entry heading and turn radius are available, otherwise the direct geodesic.
  Travel time is wind-triangle integrated across spatial samples and known
  time-varying wind changes. Impossible wind, crab-angle, minimum-groundspeed,
  or path-geometry cases fail closed.
- Divert energy includes the horizontal path plus terminal climb/descent to the
  landing-surface altitude, with the same mass/density power adjustments and
  reserve threshold used by route and RTH energy.
- Scenario `landing_zone_unavailable` events apply from their resolved route
  state onward and are evaluated at every interior state for that route leg.
- Landing-zone reachability does not score surface suitability, obstacles,
  weather at the landing surface, or communications dependency. Those remain
  separate operational inputs/checks.

## Obstacle Clearance Semantics

- `assets.obstacles_file` is loaded by the CLI when present.
- Relative obstacle paths resolve from the mission file directory.
- GeoJSON coordinates are interpreted in `[lon, lat]` order.
- Supported geometries are `Point`, `LineString`, and `Polygon`.
- `properties.height_m` is required and is interpreted as the top of the
  obstacle in metres AMSL.
- `properties.radius_m` and `properties.uncertainty_m` are optional non-negative
  metres. They expand the separation check and default to `0`.
- When an obstacle provider is configured, route legs are sampled with the same
  sub-segment midpoint machinery used for wind and population checks.
- An obstacle violation is reported when a sampled route point lies within
  `radius_m + constraints.min_obstacle_clearance_m + uncertainty_m`
  horizontally and has less than
  `constraints.min_obstacle_clearance_m + uncertainty_m` vertical clearance
  above `height_m`. Missing `min_obstacle_clearance_m` defaults to `0` for
  configured obstacle files.
- When `constraints.min_terrain_clearance_m` and `assets.terrain_file` are both
  configured, the sampled AMSL altitude must also clear terrain elevation by at
  least that value.
- Obstacle and terrain clearance failures do not make distance/time totals
  partial.
- Core execution performs no live obstacle lookups. Operator-provided obstacle
  data quality, freshness, and height reference are outside the estimator.

## Ground-Risk and SORA Footprint Semantics

- `estimate --format ground-risk` can produce a centerline diagnostic without
  a declared SORA footprint. That result is not sufficient for the operational
  `sora` command.
- SORA 2.5 requires `sora.ground_risk_footprint` with a non-blank operator
  derivation. Step 8 containment is calculated separately; no confirmation
  checkbox can substitute for that calculation.
- `operational_volume_margin_m` is the lateral distance from the modeled route
  to the outer contingency volume. `ground_risk_buffer_m` is the additional
  Ground Risk Buffer; population is assessed across their sum.
- `maximum_height_agl_m` is the declared maximum AGL height of the assessed
  operational and contingency volume. The SORA command independently resolves
  route/terrain AGL and requires this value to cover the route maximum plus the
  positive `vertical_contingency_margin_m`.
- `airspace.max_altitude_agl_m` must cover the declared maximum height. Under
  `buffer_method: initial_1_to_1`,
  `ground_risk_buffer_m` must also be at least `maximum_height_agl_m`.
- Step 8 derives a 5–35 km adjacent-area limit, operational population/assembly
  limits, and required containment robustness from Tables 8–13. Medium/high
  outcomes require a referenced Step 2 GRC re-evaluation. Annex E compliance is
  always explicitly `not_assessed`.
- `sora` requires `population-grid.v2` conservative-cell evidence with source,
  year, native/effective resolution, validity dates, assessor reference, and a
  transient-population/assemblies assessment. Legacy and WorldPop point-sampled
  grids remain diagnostic only.
- `airspace` must cite a whole operational-and-contingency-volume assessment and
  explicitly declare that its fields describe the worst case across both
  volumes. ARC-a atypical/segregated and entirely-above-FL600 booleans are
  rejected until authority and pressure-altitude evidence workflows exist.
- Only SORA version `2.5` is supported. M1(A/B/C) and M2 declarations are
  reserved, but every applied declaration is rejected until Annex B integrity
  and assurance criteria can be evaluated; free-text evidence earns no credit.
  The former M3 ERP treatment is not a ground-credit input, and a tactical
  mitigation claim does not reduce residual ARC.

## Divert Routing Semantics

Divert route estimates are computed in scenario runs when a `lost_link` event
fires and the configured `lost_link_policy.action` is `divert`.

Fields computed in `CommsLinkPolicyOutcome.divert_estimate`:

- `target_zone_id`: ID of the landing zone targeted by the divert policy.
- `distance_m`: divert path distance to the nearest point of the target zone. Uses Dubins path distance (bank-angle-constrained arc + straight) when entry heading and `vehicle.performance.turn_radius_m` are both available; otherwise straight-line geodesic distance.
- `time_s`: transit time at mission or vehicle cruise TAS (`distance_m / tas_mps`).
- `energy_wh`: deterministic cruise-power energy for the divert leg. When
  mass/density fields are configured on the vehicle profile, the same adjusted
  cruise power used by route, RTH, and landing-zone energy checks is applied.
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

Supported distribution kinds: `normal` (requires `mean` and `std > 0`) and
`uniform` (requires `low < high`). Normal distributions are supported only for
wind components; positive physical quantities require a bounded uniform with
`low > 0`.

## Monte Carlo Sampling Semantics

- Wind sampling (`wind_east_mps`, `wind_north_mps`) overrides the mission wind provider with a `ConstantWindProvider` for each sample. Spatiotemporal and layered wind providers are not used in sampled runs when wind parameters are specified.
- Cruise speed sampling overrides `mission.defaults.cruise_speed_mps` for each sample.
- Cruise power sampling overrides `vehicle.energy.cruise_power_w` for each sample.
- Battery capacity sampling overrides `vehicle.energy.battery_capacity_wh` for each sample.
- Terrain, obstacles, geofences, and landing zones are used unchanged across all samples.
- The baseline estimate is computed once before sampling with unmodified mission, vehicle, and wind provider.
- Sampling is deterministic for a given `seed`, `samples`, and parameter configuration.
- `operational_feasibility_assessed` is always `false`; this is a diagnostic
  parameter sweep.
- `modeled_constraint_pass_rate` is modeled-pass samples divided by evaluated
  samples; failed executions are excluded. It is not an operational or landing
  probability.
- `sample_count` equals `modeled_pass_sample_count + infeasible_sample_count +
  failed_sample_count`.
- `total_time_s`, `reserve_at_mission_end_wh`, and
  `reserve_at_mission_end_percent` are conditioned on modeled-pass samples.

## Diagnostic Stochastic Propagation Semantics

`stochastic.v2` / `stochastic-envelope.v2` is an open-loop diagnostic
parameter sweep, not an operational-feasibility assessment:

- `operational_feasibility_assessed` is always `false`.
- `modeled_constraint_pass_rate` is the fraction of evaluated samples whose
  independent deterministic estimator run passed the constraints supplied to
  that run. Failed samples are excluded from its denominator.
- `sample_count + infeasible_sample_count + failed_sample_count` equals the
  requested sample count. `spatial_infeasible_count` is a subset of
  `infeasible_sample_count` and must not be added again.
- `timeline`, `conditional_reserve_violation_rate`, and
  `reserve_at_mission_end_wh` include modeled-pass samples only. Every timeline
  point reports `contributing_sample_count` to make that conditioning explicit.
- Every modeled-pass sample uses its own estimated leg sequence and duration.
  Geographic interpolation is geodesic, and aggregate position uses a
  spherical centroid so antimeridian crossings do not average toward 0°.
  `route_position_centroid_*` is a reference-route proxy, not simulated flown
  position.
- `wind_process_noise_std_mps` must be `0.0`. A vehicle with a `controller`
  profile is rejected. Neither the former passive-drift wind approximation nor
  the former closed-loop path model is accepted as safety evidence.
- Normal distributions remain supported for signed wind components. Positive
  physical parameters require a bounded uniform distribution with `low > 0`;
  draws are never clipped to an invented floor.

## Output Format Semantics

`estimator-envelope.v9` and `scenario-report.v3` include a structured
`operational_readiness` verdict. `GO` requires present and feasible energy,
geofence, landing-zone, resource, link, obstacle, and weather results; a
selected resource and link; feasible RTH; ground risk at or below iGRC 7; and
no estimator warning. Missing evidence fails closed.

The field name describes readiness within this deterministic estimator surface.
It does not assert regulatory approval, current NOTAM/traffic/Remote ID/U-space
state, source-data freshness, aircraft qualification, held-out flight
validation, or SITL/HITL conformance.

This verdict controls the default process exit for `estimate`, `scenario`, and
`batch` independently of rendering. JSON, Markdown, summary, checklist,
profile, sensitivity, GeoJSON, KML, and batch CSV/per-run outputs do not change
the gate. `--engineering-only` lets a computationally feasible/pass result exit
success for non-operational analysis, but the structured readiness verdict is
still emitted where the output contract supports it.

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

Feature layers:

- `route`: one LineString per leg. Coordinates in `[lon, lat, altitude_m]` order (RFC 7946). Properties include `leg_id`, `action`, `energy_margin_pct`, `rth_reserve_margin_wh`, `rth_reserve_margin_pct`, and `rth_reserve_color` (`green` / `yellow` / `red`) when RTH reserve data is available.
- `landing_zones`: one Point per configured landing zone. Properties include `zone_id`, `reachable` (boolean), and `surface` (from GeoJSON source or `"unknown"`).
- `geofences`: one Polygon per configured geofence zone. Properties include `zone_id`, `kind` (`forbidden` / `caution`), and `conflict` (boolean).
- `obstacles`: one Point, LineString, or Polygon per configured obstacle. Properties include `height_m`, `radius_m`, `uncertainty_m`, and `conflict`.

`energy_margin_pct` is computed per leg as:
`(reserve_at_landing_wh − reserve_threshold_wh) / battery_capacity_wh × 100`.

Energy color thresholds:

- `green`: `energy_margin_pct > 30`
- `amber`: `10 ≤ energy_margin_pct ≤ 30`
- `red`: `energy_margin_pct < 10`

RTH reserve color thresholds use the same percentage bands, computed from
`reserve_margin_wh / battery_capacity_wh × 100`.

Geofence, landing-zone, and obstacle layers are omitted when the corresponding asset is not configured in the mission.

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
