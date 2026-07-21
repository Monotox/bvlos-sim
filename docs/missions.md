# Missions and vehicles

How to author every input file the CLI accepts, and what each field does at
runtime. Start from the minimal examples, add blocks as you need them, and
check your work with `--validate-only` at any point:

```bash
uv run bvlos-sim estimate mission.yaml vehicle.yaml --validate-only
```

Files may be YAML or JSON. Unknown fields are rejected everywhere except the
documented free-form `metadata` maps. Some fields are accepted for schema
stability but not consumed yet (for example `route[].acceptance_radius_m`,
`route[].loiter_radius_m`, `defaults.hover_speed_mps`,
`assets.comms_coverage_file`, `mission.policy.lost_link_policy` as a named
policy, and vehicle `mass.empty_kg`/`max_payload_kg`) — never treat them as
enforced.

## Mission (`mission.v7`)

A minimal valid mission:

```yaml
schema_version: mission.v7        # required, exactly this value
mission_id: my_survey_001
vehicle_profile: quadplane_v1     # must match the vehicle file's vehicle_id

planned_home:                     # initial state and RTL target
  lat: 52.0
  lon: 4.0
  altitude_amsl_m: 12.0

defaults:
  cruise_speed_mps: 18.0
  altitude_reference: relative_home   # relative_home | amsl | terrain

route:
  - id: takeoff
    action: vtol_takeoff
    altitude_m: 80.0
  - id: wp1
    action: waypoint
    lat: 52.001
    lon: 4.002
    altitude_m: 120.0
  - id: rtl
    action: rtl
```

Route actions: `takeoff`, `vtol_takeoff`, `waypoint`, `loiter_time` (needs
`loiter_time_s`), `land`, `rtl`. Each item needs a unique slug `id`; `lat`,
`lon`, `altitude_m`, and `altitude_reference` apply per item.
`altitude_reference: terrain` resolves altitude above ground and requires a
terrain asset.

Older files: unversioned and `mission.v6` inputs are rejected by every normal
command — run `bvlos-sim migrate mission.yaml --dry-run` first.

### Constraints

```yaml
constraints:
  min_landing_reserve_percent: 25.0   # % of battery that must survive landing
  require_rth_reserve: true           # hard per-leg return-to-home reserve gate
  max_wind_mps: 12.0                  # sustained-wind limit at every path sample
  max_crosswind_mps: 8.0              # cross-track wind limit
  min_distance_to_landing_zone_m: 2500.0
  min_obstacle_clearance_m: 15.0      # separation buffer around obstacles
  min_terrain_clearance_m: 30.0       # sampled terrain clearance (needs terrain asset)
```

All constraints fail closed. `max_gust_mps`, `min_visibility_m`, and
`max_precipitation_mm_h` are accepted, but no built-in provider supplies those
observations yet, so setting them makes the mission `INFEASIBLE`
(`WEATHER_DATA_UNAVAILABLE`) rather than silently compliant. The reserve
threshold in Wh is `battery_capacity_wh × percent / 100`, using
`min_landing_reserve_percent` when set and the vehicle's
`reserve_percent_default` otherwise.

### Estimation settings

```yaml
estimation:
  fidelity: v2                 # v1 default; v2 adds turn arcs + fixed-wing loiter
  wind_east_mps: 2.0           # constant wind (positive east/north)
  wind_north_mps: -1.0
  wind_layers:                 # altitude-banded wind; supersedes scalar wind
    - {altitude_m: 0.0, wind_east_mps: 2.0, wind_north_mps: 0.0}
    - {altitude_m: 500.0, wind_east_mps: 6.0, wind_north_mps: -1.0}
  max_segment_length_m: 500.0  # sample straight legs at bounded intervals
  min_groundspeed_mps: 3.0
```

Wind precedence, strongest first: CLI `--wind-layer` flags → mission
`assets.wind_grid_file` → `estimation.wind_layers` → scalar
`wind_east_mps`/`wind_north_mps`. Scenario `initial_conditions` override
mission `estimation` for scenario runs. Fidelity v2 does *not* enable
sub-segment sampling by itself — set `max_segment_length_m` separately (it
also works in v1).

### Assets

```yaml
departure_time: "2026-06-01T14:00:00Z"   # UTC; needed for time-windowed geofences
assets:
  terrain_file: assets/terrain.yaml
  wind_grid_file: assets/wind_grid.yaml
  geofences_file: assets/geofences.geojson
  landing_zones_file: assets/landing_zones.geojson
  obstacles_file: assets/obstacles.geojson
  population_grid_file: assets/population.yaml
```

Relative paths resolve from the mission file's directory. All assets are
offline files — core execution performs no live lookups; data quality and
freshness are the operator's responsibility. Fetch real data with the bundled
scripts (`uv sync --extra scripts`, then `scripts/fetch_all.py <lat> <lon>` or
the individual `fetch_terrain.py` / `fetch_wind.py` / `fetch_landing_zones.py`
/ `fetch_geofences.py` / `fetch_population.py`); see
[`examples/real_world/`](https://github.com/Monotox/bvlos-sim/blob/main/examples/real_world/README.md) for a complete
pre-fetched area.

**Terrain** (`terrain-grid.v1`) — uniform elevation grid, bilinear
interpolation:

```yaml
origin_lat: 51.990
origin_lon: 3.990
step_lat_deg: 0.001
step_lon_deg: 0.001
elevations_m:
  - [10.0, 10.5, 11.0]     # one row per latitude step, south to north
```

**Wind grid** (`wind-grid.v1`) — wind as a function of time, altitude, lat,
lon; quadrilinear interpolation, clamped at domain edges. Each axis must be
strictly increasing with at least 2 entries:

```yaml
axes:
  time_s: [0.0, 600.0]
  altitude_m: [0.0, 200.0]
  lat: [51.99, 52.00, 52.01]
  lon: [3.99, 4.00, 4.01]
values:                      # values[time][alt][lat][lon] = [east_mps, north_mps]
  ...
```

**Geofences** (`geofence-geojson.v1`) — GeoJSON `Polygon`/`MultiPolygon`
features, coordinates `[lon, lat]`. `properties.kind` is `forbidden` or
required; forbidden boundary contact is a conflict, required zones must cover
the route as a union. Optional properties: `floor_m`/`ceiling_m` (AMSL
altitude band; a zone only conflicts when horizontal geometry intersects *and*
altitude bands overlap) and `active_from`/`active_until`/`recurrence`
(`daily`/`weekdays`) for time-windowed zones — evaluated against
`departure_time`, and treated as always active (with a warning) when it is
missing.

**Landing zones** (`landing-zone-geojson.v1`) — `Point`/`Polygon`/
`MultiPolygon` features. `properties.altitude_amsl_m` gives the surface
elevation; without it, the terrain provider must cover the zone. Reachability
is checked at route endpoints and interior samples (≤ 50 m spacing); divert
distance uses a Dubins turn-and-straight path when heading and turn radius are
known, wind-triangle-integrated, and divert energy includes the terminal
climb/descent. Reachability does not score surface suitability or obstacles.

**Obstacles** (`obstacle-geojson.v1`) — `Point`/`LineString`/`Polygon`
features with required `properties.height_m` (top of obstacle, AMSL) and
optional `radius_m`/`uncertainty_m` expanding the separation check. A sampled
route point violates when it is horizontally within
`radius_m + min_obstacle_clearance_m + uncertainty_m` and clears the top by
less than `min_obstacle_clearance_m + uncertainty_m`.

**Population** — the diagnostic grid (`population-grid.v1`, or unversioned)
feeds `estimate --format ground-risk` only. The operational `sora` command
requires `population-grid.v2` with provenance metadata; see
[SORA evidence](#sora-evidence).

### Link systems

```yaml
link_systems:
  - link_id: c2_primary
    kind: direct          # direct | cellular | satellite | hybrid
    required: true
    priority: 1
    availability: available
    max_range_m: 8000.0
```

Deterministic, offline checks: `availability: unavailable` makes a link
infeasible; `max_range_m` is checked against the maximum distance from home at
leg endpoints. When any link is `required`, at least one required link must be
feasible; the selected link is the feasible one with the lowest priority.

## Vehicle (`vehicle.v4`)

```yaml
vehicle_id: quadplane_v1          # matched against mission.vehicle_profile
vehicle_class: vtol
characteristic_dimension_m: 1.0   # wingspan / rotor diameter / max tip distance

mass:
  empty_kg: 8.0
  max_takeoff_kg: 12.0
  operating_mass_kg: 11.0         # enables mass-scaled power when reference_mass_kg is set

performance:
  cruise_speed_mps: 18.0
  hover_speed_mps: 5.0
  max_speed_mps: 25.0             # max possible commanded speed (used for iGRC)
  climb_rate_mps: 3.0
  descent_rate_mps: 2.0
  turn_radius_m: 80.0
  max_wind_mps: 10.0              # exceeding emits a GO-blocking advisory warning
  max_crab_angle_deg: 35.0
  max_station_keep_wind_mps: 8.0

energy:
  battery_capacity_wh: 900.0
  reserve_percent_default: 25.0
  cruise_power_w: 450.0
  hover_power_w: 1200.0           # required for hover-capable loiter
  climb_power_w: 1500.0           # falls back to cruise_power_w when omitted
  # descent_power_w: 400.0        # same fallback

failsafe:
  low_battery_warn_percent: 30
  low_battery_abort_percent: 25
  emergency_land_percent: 10

capabilities:
  hover: true
  forward_flight: true

metadata:
  calibration_status: placeholder_values   # manufacturer_derived | placeholder_values | log_calibrated
  source: null
  notes: Replace with manufacturer data or measured logs before real analysis.
```

How energy is computed: legs with positive vertical motion use climb power,
negative use descent power, forward transit uses cruise power, hover loiter
uses hover power. Optional fidelity fields — `energy.reference_mass_kg`,
`energy.reference_density_kgm3`, `energy.induced_power_mass_exponent`, and
`energy.usable_capacity_curve` — add deterministic mass, ISA-density, and
usable-state-of-charge scaling; they are closed-form pre-calibration aids, not
a substitute for fitting against your own flight logs with
[`calibrate`](cli.md#calibrate).

Optional `resource_systems` replace the battery-only energy view: the mission
is resource-feasible when at least one configured system (`onboard_battery`,
`external_power` with `continuous_power_w`/`max_route_distance_m`/
`max_route_time_s`/`max_tether_length_m`, or `hybrid`) is feasible, RTH demand
included. `fuel`, `hydrogen`, and `other` are accepted but currently
unsupported.

Community profiles for real aircraft live in
[`examples/vehicles/community/`](https://github.com/Monotox/bvlos-sim/blob/main/examples/vehicles/community/README.md).
Validate any profile against your own logs before operational use.

## Scenarios (`scenario.v1`)

A scenario wraps a mission/vehicle pair with initial conditions, timeline
events, and assertions:

```yaml
schema_version: scenario.v1
scenario_id: lost-link-demo
mission_file: mission.yaml
vehicle_file: vehicle.yaml

initial_conditions:
  wind_east_mps: 3.0
  lost_link_policy:
    action: rtl               # rtl | land | loiter | divert
    loiter_s: 30.0            # loiter before acting
    # divert_target_id: zone1 # required when action is divert

events:
  - event_id: link-loss-mid
    kind: lost_link           # lost_link | observe | wind_change | landing_zone_unavailable
    trigger: at_route_item    # at_mission_start | at_route_item | at_elapsed_time | at_mission_end
    trigger_route_item_id: wp1

assertions:
  - assertion_id: reserve-ok
    kind: field_gt            # estimate_succeeds | estimate_fails | field_lt/gt/le/ge/eq
                              # | policy_action_eq | policy_divert_feasible
    field_path: estimate.energy.reserve_at_landing_wh
    expected: 100.0
```

- `wind_change` events carry scalar wind or `wind_layers` and apply from the
  trigger time onward; `landing_zone_unavailable` events need
  `unavailable_zone_ids` and re-evaluate reachability from that point.
- A `lost_link` event may carry its own `policy` block, overriding the global
  policy for that event only. Divert outcomes include a Dubins-path
  `divert_estimate` (distance, time, energy, reserve after divert,
  feasibility) in the report.
- `field_path` uses dot notation over the estimate result
  (`estimate.status`, `estimate.energy.reserve_at_landing_wh`,
  `estimate.geofence.is_feasible`, …). An unrecognized path yields an
  `unsupported` outcome whose JSON lists all valid paths; paths for
  unevaluated blocks yield `skipped`. Neither fails the scenario by itself.

## Uncertainty and stochastic plans

`uncertainty.v2` (for `sample`) and `stochastic.v2` (for `propagate`) share
the same five samplable parameters; unset parameters hold their deterministic
value:

```yaml
schema_version: uncertainty.v2      # or stochastic.v2
uncertainty_id: wind-sweep          # propagation_id for stochastic.v2
mission_file: mission.yaml
vehicle_file: vehicle.yaml
samples: 200                        # stochastic.v2 max 10 000, plus dt_s and
seed: 42                            # wind_process_noise_std_mps: 0.0
parameters:
  wind_east_mps:  {kind: normal, mean: 0.0, std: 2.0}
  wind_north_mps: {kind: normal, mean: 0.0, std: 2.0}
  cruise_speed_mps:    {kind: uniform, low: 14.0, high: 22.0}
  cruise_power_w:      {kind: uniform, low: 400.0, high: 500.0}
  battery_capacity_wh: {kind: uniform, low: 850.0, high: 950.0}
```

`normal` (fields `mean`, `std > 0`) is allowed for wind components only;
positive physical parameters require a bounded `uniform` with `low > 0` —
draws are never clipped to an invented floor. Runs are deterministic for a
fixed seed.

## SORA evidence

The `sora` command refuses to guess. Beyond a population grid it requires
three mission blocks, all explicit:

```yaml
airspace:
  class: "G"
  max_altitude_agl_m: 130.0
  operational_and_contingency_volume_assessment_reference: "Airspace study AS-014 rev 2"
  worst_case_arc_declared: true
  aerodrome_environment: false          # mandatory boolean (Annex I definition)
  atypical_or_segregated: false         # true is rejected without authority evidence
  over_urban_area: false
  transponder_mandatory_zone: false     # mandatory boolean
  entirely_above_flight_level_600: false

sora:
  version: "2.5"                        # only supported revision
  ground_risk_footprint:
    operational_volume_margin_m: 30.0   # route to outer contingency volume
    ground_risk_buffer_m: 130.0         # initial 1:1 GRB >= maximum_height_agl_m
    maximum_height_agl_m: 130.0         # must cover route AGL + vertical margin
    buffer_method: initial_1_to_1
    vertical_contingency_margin_m: 10.0
    derivation: "Operational volume and GRB study GRB-2026-014"
  containment_evidence:
    assessment_reference: "Adjacent-area study CONT-2026-004"
    average_population_density_ppl_km2: 1200.0
    largest_outdoor_assembly: below_40000
    sheltering_applicable: true
  ground_risk_mitigations:
    m1a_sheltering:               {applied: false, robustness: none}
    m1b_operational_restrictions: {applied: false, robustness: none}
    m1c_ground_observation:       {applied: false, robustness: none}
    m2_impact_reduction:          {applied: false, robustness: none}
```

The population evidence must be `population-grid.v2`: conservative source-cell
maxima plus metadata with `source`, `population_year`,
`native_resolution_m`/`effective_resolution_m`,
`value_semantics: conservative_cell_maximum`, an
`authority_assessment_reference`, a `valid_from`/`valid_until` window
containing `departure_time`, and a transient-population/assemblies assessment.
WorldPop point samples and legacy grids stay diagnostic-only.

Every `applied: true` mitigation is rejected until an Annex B criteria
evaluator exists, so the final GRC equals the intrinsic GRC. Population
density exactly at a band boundary (for example 50,000 ppl/km²) is assigned to
the stricter band. Medium/high containment requires a reference showing the
GRB was fed back through Step 2; Annex E compliance is always
`not_assessed`.

## Contracts and versioning

Input schemas (`mission.v7`, `vehicle.v4`, `scenario.v1`, `uncertainty.v2`,
`stochastic.v2`, `batch.v1`, the GeoJSON asset schemas, `population-grid.v2`)
and output envelopes (`estimator-envelope.v9`, `scenario-report.v3`, and the
rest printed by [`schema-versions`](cli.md#schema-versions)) are stable public
contracts. Within a published version, fields are not removed or renamed, enum
and exit-code meanings do not change, and canonical JSON rendering stays
byte-stable — representative outputs are pinned by golden fixtures. When a
change is intentional, the version identifier bumps and fixtures, tests, and
docs move in the same commit (see
[CONTRIBUTING](https://github.com/Monotox/bvlos-sim/blob/main/CONTRIBUTING.md)).
