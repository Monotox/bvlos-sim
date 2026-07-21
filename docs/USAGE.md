# Usage

This guide covers the supported CLI and Python API workflows for bvlos-sim.

## Prerequisites

- Python 3.12+
- Dependencies installed with `uv`

```bash
uv sync
```

Mission, vehicle, scenario, uncertainty, and batch files may be `.yaml`,
`.yml`, or `.json`. Relative asset paths are resolved from the referencing
file's directory.

Every mission file consumed by `estimate`, `scenario`, `batch`, `sora`,
`validate`, `export`, or `sitl` must explicitly declare
`schema_version: mission.v7`. Normal loaders do not guess a missing version.
Use `bvlos-sim migrate` for an unversioned or `mission.v6` mission before
running those commands.

Verify the CLI:

```bash
uv run bvlos-sim --help
```

## CLI Commands

bvlos-sim exposes seventeen canonical project commands from a source checkout,
plus `contracts` as an alias for `schema-versions` (published wheels omit the
developer-only `bump` command):

- `estimate`: run deterministic mission estimation and static feasibility checks
- `size-battery`: compute the minimum battery capacity needed for feasibility
- `scenario`: run deterministic scenario events and assertions
- `convert`: convert a QGroundControl `.plan` file to a `mission.v7` YAML
- `export`: convert a `mission.v7` YAML to a QGroundControl `.plan` file
- `migrate`: upgrade legacy `mission.v6` inputs to `mission.v7`
- `batch`: run batch mission estimates from a manifest file
- `sample`: run seeded Monte Carlo uncertainty sampling
- `propagate`: run time-stepped stochastic particle propagation with EKF and tracking controller
- `sitl`: build a contract-only or live SITL evidence bundle from an existing scenario
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations
- `sora`: run the SORA pre-assessment (Ground Risk, Air Risk, and SAIL)
- `ingest-log`: normalize ArduPilot DataFlash or PX4 ULog controller logs
- `validate`: compare a predicted mission estimate against an observed flight trace
- `calibrate`: fit a calibration profile from a base vehicle and observed flight traces
- `schema-versions` (alias `contracts`): print supported input/output contract versions as JSON
- `bump`: bump the project version and roll the changelog (release tooling)

| Command | Exit 0 | Exit 10 | Exit 11 | Exit 12 | Exit 13 |
|---------|--------|---------|---------|---------|---------|
| estimate | operational GO, or engineering-only computational success | computationally infeasible or operational NO-GO | invalid input | unsupported | internal error |
| size-battery | sizing succeeded | - | invalid input | - | internal error |
| scenario | operational GO, or engineering-only computational pass | failed or operational NO-GO | invalid input | - | internal error |
| sample | success | - | invalid input | - | internal error |
| propagate | success | - | invalid input | - | internal error |
| sitl | success | - | invalid input/asset | - | adapter runtime/write error |
| compare | passed | drifted/failed | invalid input | unsupported (contract-only) | internal/write error |
| convert | success | - | invalid input | - | internal error |
| migrate | success | - | invalid input | - | - |
| export | success | - | invalid input | - | internal error |
| batch | all operational GO, or engineering-only computationally feasible | any infeasible or operational NO-GO | invalid input/run | - | internal error |
| sora | in-scope assessment | out-of-scope Step 8, GRC > 7, or infeasible mission | invalid input | unsupported estimator failure | internal error |
| ingest-log | success | - | invalid/unsupported log | - | internal error |
| validate | within thresholds | outside validation thresholds | invalid input | - | internal error |
| calibrate | success | - | invalid input | - | internal error |
| schema-versions | success | - | - | - | - |
| bump | success / consistent | - | invalid input / drift | - | internal error |

[`CLI_EXIT_CODES.md`](CLI_EXIT_CODES.md) is the authoritative per-command
reference. `estimate`, `scenario`, and `batch` apply their operational readiness
gate for every output format; choosing JSON, Markdown, summary, checklist,
profile, sensitivity, GeoJSON, KML, or CSV never changes the exit verdict. Note
the divergences a programmatic caller must branch on carefully:
`sample` and `propagate` always exit `0` once a run completes (feasibility is in
the body, never `10`), `scenario` has no `12` (every non-passed outcome collapses
to `10`), and `estimate` returns `11` for a computed invalid-input failure even
when the input files are valid.

A run interrupted by `SIGTERM`/`SIGINT` exits `14` (`CANCELLED`). All `--output`
writes are atomic (temp file then `os.replace`), so interruption never leaves a
truncated file. Depending on whether the signal arrived before or after the
atomic commit point, the destination is absent, retains its prior content, or
contains the new complete artifact.

Mission-scoped functionality is exposed through `estimate` by mission and
vehicle YAML: fidelity settings, terrain, wind grids, geofences, landing zones,
obstacles, resource systems, communication links, energy feasibility, and route
geometry.
Scenario events, uncertainty sampling, and SITL evidence use `scenario`,
`sample`, and `sitl` because they require separate versioned input contracts.
SITL comparison reports are exposed through `compare` so evidence review has a
dedicated command with JSON, Markdown, and `--output` support.
Plan conversion is bidirectional: `convert` imports a QGC `.plan` to YAML and
`export` writes a YAML back to a QGC `.plan`. Multi-run CI workflows are exposed
through `batch`.
For terse terminal output, `estimate`, `scenario`, `sample`, and `propagate`
support `--format summary`. `estimate` and `scenario` support `--format geojson`
and `--format kml` for map-ready route exports. `batch` supports `--format
geojson|kml` when used with `--output-dir` to write one map file per run.
`sitl` and `compare` remain JSON/Markdown only.

`estimate` and `scenario` support `--format checklist` as a human-readable view
of the same structured operational verdict used by every format. Each check is
rendered on one line with a `✓`/`✗`/`◌` icon, and the output ends with
`Status: GO` or `Status: NO-GO`. The verdict is fail-closed: every energy,
geofence, landing-zone, resource, link, obstacle, weather, RTH, and ground-risk
result must be present and acceptable, and warnings must be empty. Missing
evidence is `NO-GO`, not an implicit pass.

This is the estimator's deterministic planning/preflight verdict. It is not a
regulatory authorization or a complete operational safety case, and it does not
attest live NOTAM/traffic/Remote ID/U-space state, source-data freshness,
aircraft qualification, flight validation, or SITL/HITL evidence.

Pass `--engineering-only` to `estimate`, `scenario`, or `batch` only when a
computationally feasible/pass result should exit `0` despite missing or failed
operational evidence. This flag changes the process/batch status, not the
calculation or evidence: `estimator-envelope.v9` and `scenario-report.v3` still
carry `operational_readiness` with `verdict`, `missing_evidence`,
`failed_checks`, and `warning_codes`.

`batch` also supports `--format csv` to emit a comma-separated table
(id, status, reserve_margin_percent, flight_time_s, warning_count) for
import into spreadsheets. This outputs to stdout; use `--output` to redirect
to a file.

All commands that load input files support `--validate-only`: load
and validate all input files against their schemas and exit without running the
estimator. Exits 0 on success, 11 (invalid input) otherwise. Useful in CI to
catch schema errors before long runs. `estimate`, `scenario`, `sample`,
`propagate`, `sora`, `size-battery`, and `batch` also validate referenced
mission assets (geofence, landing-zone, terrain, population, obstacle,
wind-grid) in this mode, so a broken asset path fails preflight instead of at
run time. `calibrate`, `compare`, and `size-battery` accept `--validate-only`
too.

```bash
uv run bvlos-sim estimate mission.yaml vehicle.yaml --validate-only
# mission: mission.yaml: OK
# vehicle: vehicle.yaml: OK

uv run bvlos-sim batch manifest.yaml --validate-only
# batch: manifest.yaml: OK (3 runs)
#   mission: mission_a.yaml: OK
#   vehicle: vehicle_a.yaml: OK
#   ...

uv run bvlos-sim convert plan.plan --vehicle-profile quadplane_v1 --validate-only
# plan: plan.plan: OK (4 route items)
```

### Preflight Validation (JSON)

For a machine-readable preflight, add `--validate-format json` to any
`--validate-only` run. Instead of plain-text "OK" lines it emits a
`preflight-validation.v1` envelope with one entry per file (including referenced
assets), so a backend can validate inputs before queuing a job and parse the
result instead of scraping stdout. Plain text stays the default; the envelope is
opt-in. Exit codes are unchanged: `0` when every file validates, `11` when any
file fails.

```bash
uv run bvlos-sim estimate mission.yaml vehicle.yaml --validate-only --validate-format json
```

A passing run (`ok` is the AND over every file check; `generated_at` is always
null so the output is deterministic):

```json
{
  "command": "estimate",
  "files": [
    {"error": null, "ok": true, "path": "mission.yaml", "role": "mission", "stage": null},
    {"error": null, "ok": true, "path": "vehicle.yaml", "role": "vehicle", "stage": null},
    {"error": null, "ok": true, "path": "geofences/demo.geojson", "role": "geofence", "stage": null}
  ],
  "generated_at": null,
  "ok": true,
  "schema_version": "preflight-validation.v1"
}
```

A failure pins the offending file with a stable `stage` (`schema`, `asset-load`,
or `reference`) and `code`; a missing asset and a malformed one carry distinct
codes:

```json
{
  "command": "estimate",
  "files": [
    {"error": null, "ok": true, "path": "mission.yaml", "role": "mission", "stage": null},
    {"error": null, "ok": true, "path": "vehicle.yaml", "role": "vehicle", "stage": null},
    {
      "error": {"code": "ASSET_FILE_MISSING", "detail": null, "message": "Unable to read geofence file."},
      "ok": false,
      "path": "missing.geojson",
      "role": "geofence",
      "stage": "asset-load"
    }
  ],
  "generated_at": null,
  "ok": false,
  "schema_version": "preflight-validation.v1"
}
```

This is preflight only — it loads and schema-checks inputs and never runs the
estimator, scenario, or sampler. It is distinct from the standalone `validate`
command, which is a predicted-vs-observed accuracy report.

Command help:

```bash
uv run bvlos-sim estimate --help
uv run bvlos-sim size-battery --help
uv run bvlos-sim scenario --help
uv run bvlos-sim convert --help
uv run bvlos-sim batch --help
uv run bvlos-sim sample --help
uv run bvlos-sim propagate --help
uv run bvlos-sim sitl --help
uv run bvlos-sim compare --help
```

## QGroundControl Plan Conversion

Convert a QGroundControl `.plan` JSON file into a starter `mission.v7` YAML.
`--vehicle-profile` is required and must match the `vehicle_id` in the vehicle
profile YAML you intend to use with `estimate` or `scenario`:

```bash
uv run bvlos-sim convert examples/missions/pipeline_demo_001.plan \
  --vehicle-profile quadplane_v1 \
  --output /tmp/pipeline_converted.yaml
```

The converter reads `plannedHomePosition`, mission `cruiseSpeed` and
`hoverSpeed`, and supported MAVLink mission items: takeoff, VTOL takeoff,
waypoint, loiter-time, RTL, land, and VTOL land. Unsupported commands and
ComplexItem entries are skipped with warnings to stderr so the rest of the
route can still be converted.

`MAV_CMD_NAV_TAKEOFF` (command 22) is normalised to `vtol_takeoff` in the
output YAML and a diagnostic is emitted to stderr:

```
Warning: item 0 (command 22): MAV_CMD_NAV_TAKEOFF (22) normalised to vtol_takeoff;
fixed-wing-only takeoff is not a separate action in mission.v7. Review vehicle_class
after converting.
```

If your `.plan` file was designed for a fixed-wing-only aircraft rather than a VTOL,
review the `vehicle_class` field in the output YAML and in your vehicle profile.

The output YAML sets `vehicle_profile` to the value you supplied and omits
policy and asset references. Review route altitudes and constraints, and add
any geofence, landing-zone, terrain, or wind-grid assets before treating the
converted mission as operational input.

To validate the `.plan` file without writing output:

```bash
uv run bvlos-sim convert plan.plan --vehicle-profile quadplane_v1 --validate-only
```

## QGC Mission Export

`export` is the inverse of `convert`: it turns a `mission.v7` YAML into a
QGroundControl `.plan` JSON file so a mission authored in bvlos-sim can be
uploaded to an aircraft via QGC or MAVLink.

```bash
uv run bvlos-sim export examples/missions/pipeline_demo_001.yaml \
  --output /tmp/pipeline_demo_001.plan
uv run bvlos-sim export examples/missions/pipeline_demo_001.yaml   # JSON to stdout
```

Route items map to MAVLink mission commands:

| bvlos-sim action | QGC command |
|---|---|
| `vtol_takeoff` | `MAV_CMD_NAV_VTOL_TAKEOFF` (84) |
| `waypoint` | `MAV_CMD_NAV_WAYPOINT` (16), `acceptance_radius_m` → param 2 |
| `loiter_time` | `MAV_CMD_NAV_LOITER_TIME` (19), time → param 1, radius → param 3 |
| `land` | `MAV_CMD_NAV_LAND` (21) |
| `rtl` | `MAV_CMD_NAV_RETURN_TO_LAUNCH` (20) |

The altitude reference selects the MAVLink frame: `relative_home` → frame 3
(`MAV_FRAME_GLOBAL_RELATIVE_ALT`), `amsl` → frame 0 (`MAV_FRAME_GLOBAL`). An
`altitude_reference: terrain` item has no direct QGC frame, so it is exported as
relative-altitude (frame 3) and a warning is written to stderr.

bvlos-sim-specific fields (`constraints`, `assets`, `policy`) have no QGC
equivalent and are omitted from the export — they remain in the source YAML.
A note is written to stderr when any are present. The exported `.plan`
round-trips back through `convert`, preserving route item count and waypoint
coordinates.

To validate exportability without writing output:

```bash
uv run bvlos-sim export examples/missions/pipeline_demo_001.yaml --validate-only
```

## Mission Schema Migration

`mission.v7` makes the mission contract explicit and changes SORA semantics.
The normal mission loader requires the root field
`schema_version: mission.v7`; it does not silently treat an unversioned file as
current. Upgrade an unversioned/`mission.v6` file with:

```bash
uv run bvlos-sim migrate mission.yaml --dry-run
uv run bvlos-sim migrate mission.yaml --backup
uv run bvlos-sim migrate mission.yaml --output mission-v7.yaml
uv run bvlos-sim migrate missions/ --glob "*.yaml" --backup
```

Only the migration command treats a missing version as legacy `mission.v6`.
The migration adds `schema_version: mission.v7`. It refuses semantic guesses:
SORA 2.0 blocks cannot be relabelled as 2.5, and applied legacy M1/M2/M3
declarations, tactical ARC credits, strategic boolean ARC credits, ambiguous
FL600 values, or missing urban/rural classification require an operator
reassessment. A dry run prints the detected/target versions and a
diff without writing; `--backup` writes `FILE.bak` before an in-place update.

## Batch Estimates

Run multiple estimate jobs from a `batch.v1` manifest:

```bash
uv run bvlos-sim batch examples/batch/demo_batch.yaml
```

Manifest files are YAML or JSON:

```yaml
format_version: "batch.v1"
runs:
  - id: alpine_standard
    mission: ../real_world/alpine_mission.yaml
    vehicle: ../real_world/quadplane_v1.yaml
  - id: alpine_infeasible
    mission: ../real_world/alpine_infeasible.yaml
    vehicle: ../real_world/quadplane_small_battery.yaml
```

Paths are resolved relative to the manifest file. The command always prints a
table with run id, status, reserve margin above or below threshold, and flight
time, followed by a feasible/infeasible/error count. Use `--output-dir DIR` to
write per-run output files for CI collection; `--format` controls those files
while the table stays on stdout. Supported per-run file formats:

- `--format json` — one `estimator-envelope.v9` JSON file per run (`.json`)
- `--format markdown` — one Markdown report per run (`.md`)
- `--format summary` — one one-line summary per run (`.txt`)
- `--format geojson` — one GeoJSON map export per run (`.geojson`) with the
  same route/landing-zone/geofence layers as `estimate --format geojson`
- `--format kml` — one KML map export per run (`.kml`)

By default, batch labels a run feasible only when its fail-closed operational
readiness verdict is `GO`. It exits `0` only when all runs are operational GO,
`10` when any run is computationally infeasible or operational NO-GO and no
run had an input error, `11` when any run cannot load its inputs, and `13` for
unexpected internal failures. `--engineering-only` restores computational
feasibility as the per-run success criterion; it does not remove structured
readiness data from JSON outputs.

`batch` supports machine-readable progress for non-interactive workers — see
[Run Progress (JSONL)](#run-progress-jsonl) below. One record is emitted per
completed run, with `total` equal to the number of runs in the manifest.

## Mission Estimation

Run the example mission:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml
```

By default, the command writes canonical JSON to stdout.

The default exit status is operational, not renderer-specific: a successful
calculation exits `10` when required evidence is missing or a readiness check
fails, even though the selected artifact is still written. Add
`--engineering-only` only for non-operational analysis that should exit `0` on
computational feasibility.

Write JSON to a file:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --output /tmp/bvlos-report.json
```

Write Markdown:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format markdown \
  --output /tmp/bvlos-report.md
```

Write a one-line summary:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format summary
```

Example output:

```text
FEASIBLE   reserve 281.6 %   flight 2m 49s   warnings 4
```

The `warnings N` field appears when the estimate has advisory warnings
(see [Advisory Warning Codes](#advisory-warning-codes)).

Write GeoJSON route layers:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format geojson \
  --output /tmp/bvlos-route.geojson
```

Write KML route layers:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format kml \
  --output /tmp/bvlos-route.kml
```

## Return-to-Home Reserve Checks

When a mission has a `planned_home`, deterministic energy output includes an
RTH reserve timeline. Each point answers: after completing this leg, how much
energy remains after flying home at cruise TAS and cruise power, minus the
configured reserve threshold? When the current heading and vehicle turn radius
are available, the return follows a materialized Dubins turn-and-straight path;
otherwise it uses the direct geodesic. Both forms are spatially sampled and
integrate the local wind triangle, including time-varying wind. An impossible
wind triangle, excessive crab angle, or subminimum groundspeed fails closed.

JSON result fields:

- `result.energy.rth_reserve_timeline`: one point per route leg with
  `rth_distance_m`, `rth_energy_wh`, `energy_remaining_before_rth_wh`,
  `reserve_after_rth_wh`, `reserve_margin_wh`, and `is_feasible`
- `result.rth_is_feasible`: `true` only when every timeline point preserves the
  reserve threshold after a hypothetical RTH

Markdown reports include an **RTH Reserve Timeline** table:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format markdown
```

GeoJSON route features include `rth_reserve_margin_wh`,
`rth_reserve_margin_pct`, and `rth_reserve_color` (`green`, `yellow`, `red`)
when the timeline is available.

RTH reserve is a hard feasibility gate by default. It supplements rather than
replaces the landing reserve check:

```yaml
constraints:
  min_landing_reserve_percent: 25.0
  require_rth_reserve: true
```

The first RTH timeline point whose
`reserve_margin_wh` is negative makes the estimate `INFEASIBLE` with
`RTH_RESERVE_BELOW_THRESHOLD` in diagnostics. The failure is attributed to the
first failing leg and includes the RTH distance, RTH energy, reserve after RTH,
reserve margin, and reserve threshold in its context. The CLI returns the
standard infeasible exit code.

Set `require_rth_reserve: false` only for explicitly non-operational engineering
analysis. The checklist remains conservative: an absent or failed RTH result is
still `NO-GO` even when the estimator-level gate is disabled.

## Time-Varying Geofences

Geofence GeoJSON features can carry optional activation windows. Use these for
temporary flight restrictions, curfew zones, or airspace reservations that are
only active during part of the planned flight window.

Mission departure time:

```yaml
departure_time: "2026-06-01T14:00:00Z"
```

Geofence feature properties:

```json
{
  "kind": "forbidden",
  "floor_m": 120.0,
  "ceiling_m": 400.0,
  "active_from": "2026-06-01T20:00:00Z",
  "active_until": "2026-06-01T22:00:00Z",
  "recurrence": "daily"
}
```

| Property | Description |
|----------|-------------|
| `floor_m` | Optional AMSL lower bound in metres. Omitted means active down to negative infinity. |
| `ceiling_m` | Optional AMSL upper bound in metres. Omitted means active upward to infinity. |
| `active_from` | Optional ISO-8601 UTC start time. Omitted means active from the beginning of the mission window. |
| `active_until` | Optional ISO-8601 UTC end time. Omitted means active after `active_from`. |
| `recurrence` | Optional `daily` or `weekdays`; when set, the times of day recur on matching dates. |

Altitude bounds are inclusive and evaluated against each leg's AMSL altitude
band from `start_alt_amsl_m` to `end_alt_amsl_m`. A forbidden zone only blocks a
leg when the horizontal geometry intersects and the altitude bands overlap. A
required zone must cover both the horizontal segment and the full leg altitude
band. `floor_m` and `ceiling_m` can be omitted independently; when both are
present, `ceiling_m` must be greater than `floor_m`.

If a zone has any time-window property but the mission omits `departure_time`,
the estimator emits `DEPARTURE_TIME_MISSING` and treats the zone as always
active. Zones without time-window properties keep the historical always-active
behavior. `--format checklist` shows the mission departure time when it is set.

## Weather Minimums (GO/NO-GO)

Mission constraints can declare operational weather limits. When a wind provider
is configured (constant, layered, or a spatiotemporal grid), the estimator
enforces them against all per-leg path samples and returns `INFEASIBLE` if a
limit is exceeded — turning "energy OK" into "energy OK **and** weather within
approved limits".

```yaml
constraints:
  max_wind_mps: 12.0          # sustained wind; exceeding -> WIND_LIMIT_EXCEEDED
  max_crosswind_mps: 8.0      # wind component across a leg's ground track ->
                              # CROSSWIND_LIMIT_EXCEEDED
  max_gust_mps: 15.0          # requires a provider that supplies gust data
  min_visibility_m: 5000.0    # requires visibility observations
  max_precipitation_mm_h: 0.0 # requires precipitation observations
```

Enforcement notes:

- `max_wind_mps` and `max_crosswind_mps` are enforced at every route-path
  sample, including turn arcs. The first exceeded leg makes the mission
  `INFEASIBLE` with the corresponding failure code in the result diagnostics.
- When no wind provider is configured, the limits are accepted but **not
  enforced** (consistent with other provider-dependent checks); no weather block
  appears.
- The built-in providers do not supply gust, visibility, or precipitation
  observations. Configuring any corresponding limit therefore fails closed as
  `INFEASIBLE` with `WEATHER_DATA_UNAVAILABLE`; the estimator never treats a
  missing observation as compliant weather.

The `--format checklist` output gains a **Weather limits** row showing the
worst-case wind and the leg where it occurs, and `--format summary` adds a
`weather FAIL` field when a limit is exceeded. The `--format json` result
envelope includes a `weather` block with the worst observed values and any
violations, and `--format markdown` includes a **Weather Feasibility** section
(with a violations table when limits are exceeded). Weather feasibility is also
assertable from scenarios via `estimate.weather.is_feasible` and
`estimate.weather.worst_wind_speed_mps`.

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --wind-layer 0:6:0 \
  --format checklist
```

The Weather-limits row reports the worst wind and the leg where it occurs:

```text
✓ Weather limits            PASS   worst wind 6.00 m/s at leg 1 (wp1)
```

A wind above `constraints.max_wind_mps` makes the mission `INFEASIBLE` with
`WIND_LIMIT_EXCEEDED`; the checklist then shows `✗ Weather limits FAIL` and
`Status: NO-GO`.

## Obstacle and Terrain Clearance

Missions can reference an offline obstacle GeoJSON file and request deterministic
vertical-clearance checks along sampled route legs. The core estimator performs
no live lookups; obstacle quality, freshness, and height reference remain the
operator's responsibility.

```yaml
constraints:
  min_obstacle_clearance_m: 15.0
  min_terrain_clearance_m: 30.0
assets:
  obstacles_file: assets/obstacles.geojson
  terrain_file: terrain/pipeline_terrain.yaml
```

Obstacle GeoJSON (`obstacle-geojson.v1`) supports `Point`, `LineString`, and
`Polygon` features. Each feature must define `properties.height_m`, interpreted
as top-of-obstacle altitude in metres AMSL. Optional `radius_m` and
`uncertainty_m` expand the horizontal and vertical separation check.

```json
{
  "type": "Feature",
  "id": "mast-midpoint",
  "properties": {
    "height_m": 105.0,
    "radius_m": 20.0,
    "uncertainty_m": 5.0
  },
  "geometry": {
    "type": "Point",
    "coordinates": [4.001, 52.0005]
  }
}
```

When a sampled route point is inside the configured horizontal buffer and its
AMSL altitude is below `height_m + min_obstacle_clearance_m + uncertainty_m`,
the estimate returns `INFEASIBLE` with `OBSTACLE_CLEARANCE_VIOLATED`. When
`constraints.min_terrain_clearance_m` and a terrain provider are both present,
the same leg sampling verifies terrain clearance between waypoints and can
return `TERRAIN_CLEARANCE_VIOLATED`.

The result appears as `result.obstacle` in JSON, an **Obstacle Clearance**
Markdown section, an **Obstacle clearance** checklist row, `obstacle FAIL` in
summary output, and an optional `obstacles` layer in GeoJSON exports. Use the
opt-in fetch helper as a starting point only:

```bash
uv run python scripts/fetch_obstacles.py 51.99 52.01 3.99 4.01 \
  --base-altitude-amsl-m 12 \
  --output examples/missions/assets/obstacles.geojson
```

## Ground Risk (SORA iGRC)

Use `estimate --format ground-risk` to compute a SORA intrinsic Ground Risk
Class pre-assessment from an offline population-density grid and the vehicle
maximum characteristic dimension and maximum possible commanded speed.

This output is the *intrinsic* Ground Risk Class only: it does not apply M1/M2
mitigations, Air Risk Class, or SAIL. The `sora` command adds an unmitigated ARC,
SAIL, and Table 14 OSO view. Ground-mitigation credit remains fail-closed until
the tool can evaluate the Annex B integrity and assurance criteria. Both outputs
remain pre-assessment aids, not certified SORA determinations.

Without `sora.ground_risk_footprint`, `estimate --format ground-risk` assesses a
conservative route-centerline diagnostic only. The operational `sora` command
fails closed unless the mission declares the assessed operational/contingency
margin and Ground Risk Buffer (GRB); centerline-only population results are not
accepted as a SORA footprint.

Mission asset:

```yaml
assets:
  population_grid_file: assets/pipeline_population_grid.yaml
```

Diagnostic population grid format (unversioned legacy/`population-grid.v1`):

```yaml
origin_lat: 51.99
origin_lon: 3.99
step_lat_deg: 0.01
step_lon_deg: 0.01
density_ppl_km2:
  - [12.0, 12.0, 12.0]
  - [12.0, 12.0, 12.0]
  - [12.0, 12.0, 12.0]
```

Vehicle field:

```yaml
characteristic_dimension_m: 1.0
performance:
  max_speed_mps: 25.0
```

Diagnostic grids use a bilinear planning surface and are accepted by
`estimate --format ground-risk`, but not by `sora`. The WorldPop fetch helper
also produces point-sampled diagnostic data; arbitrary sampling can miss
native-raster peaks.

`max_speed_mps` is the designer-defined maximum possible commanded airspeed,
not a lower mission speed limit. Population density exactly equal to
50,000 people/km² is conservatively assigned to the highest density band.

| Flag | Description |
|------|-------------|
| `--format ground-risk` | Markdown iGRC table with mission and per-leg values |
| `--format geojson` | Adds `igrc` to route-leg properties when ground risk is computed |
| `--format checklist` | Adds a "Ground risk class" row |

Example:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001_ground_risk.yaml \
  examples/vehicles/quadplane_v1_ground_risk.yaml \
  --format ground-risk
```

Example output excerpt:

```text
# Ground Risk Class

- Characteristic dimension m: `1.00`
- Mission iGRC: `3`

| Leg | Route Item ID | Max Density (ppl/km^2) | iGRC |
|----:|---------------|------------------------:|------|
| 1 | wp1 | 12.00 | 3 |
```

## SORA Pre-Assessment

The `sora` command identifies SORA 2.5 planning requirements: it reuses the
estimator's Ground Risk Class, derives ARC and SAIL, calculates Step 8 adjacent-
area limits and containment robustness from Tables 8–13, and emits all 17 Table
14 OSO rows. It does **not** assess Annex E containment compliance or OSO
compliance, and therefore never represents a complete SORA.

This output is a planning aid, not an authorization or certified determination.
Out-of-scope Step 8 results and GRC values above 7 return exit code `10`; JSON is
still written so the reason remains auditable.

Mission airspace descriptor:

```yaml
airspace:
  class: "G"                  # ICAO airspace class at operational altitude
  max_altitude_agl_m: 130.0   # worst-case whole-volume ceiling above ground
  operational_and_contingency_volume_assessment_reference: "Airspace study AS-014 rev 2"
  worst_case_arc_declared: true
  aerodrome_environment: false  # explicit SORA Annex I whole-volume result
  atypical_or_segregated: false  # true unsupported without authority evidence workflow
  over_urban_area: false      # required for uncontrolled operations <= 500 ft
  transponder_mandatory_zone: false  # Mode-C veil or TMZ
  entirely_above_flight_level_600: false  # true unsupported without pressure-altitude evidence
  strategic_mitigation: false    # reserved; boolean ARC credit is rejected
```

The SAIL requires complete population and terrain coverage, both
`vehicle.characteristic_dimension_m` and `vehicle.performance.max_speed_mps`,
an `airspace` descriptor, and an explicit `sora.ground_risk_footprint`. Under
the supported initial 1:1 method, `ground_risk_buffer_m` must be at least
`maximum_height_agl_m`. The command independently bounds route AGL from the
terrain asset and requires the declared height to cover that route plus the
positive vertical contingency margin. Missing footprint coverage or required
descriptors make the assessment invalid; they are not converted to zero
population or advisory-only partial results. The airspace block likewise needs
a non-blank reference covering both volumes and an explicit declaration that all
classification inputs describe the worst case anywhere in those volumes.
`aerodrome_environment` and `transponder_mandatory_zone` are mandatory booleans: both
conditions can increase ARC, so omission is rejected instead of being treated
as `false`. `aerodrome_environment` follows the exact Annex I definition,
including the applicable airport/heliport distances and Class A–E Mode-C
veil/TMZ case.

The operational command accepts only `population-grid.v2` evidence. It requires
source/year/resolution provenance, conservative source-cell maxima, a validity
window containing `mission.departure_time`, an authority/assessor reference,
and a transient-population/assemblies assessment. When assemblies are present
in the operational footprint, the iGRC calculation is conservatively forced
into the assemblies-of-people density band.

```yaml
schema_version: population-grid.v2
origin_lat: 51.99
origin_lon: 3.99
step_lat_deg: 0.01
step_lon_deg: 0.01
density_ppl_km2:
  - [12.0, 12.0, 12.0]
  - [12.0, 12.0, 12.0]
  - [12.0, 12.0, 12.0]
metadata:
  source: "Authority-approved conservative population map"
  population_year: 2026
  native_resolution_m: 100.0
  effective_resolution_m: 100.0
  value_semantics: conservative_cell_maximum
  authority_assessment_reference: "POP-2026-014"
  valid_from: 2026-01-01T00:00:00Z
  valid_until: 2026-12-31T23:59:59Z
  transient_population_assessment_reference: "EVENTS-2026-008"
  operational_footprint_assemblies_present: false
```

### Mitigations (currently fail-closed)

Real SORA outcomes hinge on mitigation integrity and assurance criteria. A
robustness label plus a free-text dossier reference does not establish those
criteria. For that reason, the operational assessment rejects every applied
M1(A), M1(B), M1(C), or M2 declaration until an Annex B criteria evaluator is
implemented. A no-mitigation intrinsic assessment remains usable:

```yaml
sora:
  version: "2.5"                 # only coherently implemented revision
  ground_risk_footprint:
    operational_volume_margin_m: 30.0  # route to outer contingency volume
    ground_risk_buffer_m: 130.0         # initial 1:1 GRB
    maximum_height_agl_m: 130.0         # route AGL plus contingency
    buffer_method: initial_1_to_1
    vertical_contingency_margin_m: 10.0
    derivation: "Operational volume and initial GRB study GRB-2026-014"
  containment_evidence:
    assessment_reference: "Adjacent-area study CONT-2026-004"
    average_population_density_ppl_km2: 1200.0
    largest_outdoor_assembly: below_40000
    sheltering_applicable: true
    ground_risk_buffer_revalidation_reference: "Step 2 recheck GRC-2026-019"
  ground_risk_mitigations:
    m1a_sheltering:               { applied: false, robustness: none }
    m1b_operational_restrictions: { applied: false, robustness: none }
    m1c_ground_observation:       { applied: false, robustness: none }
    m2_impact_reduction:          { applied: false, robustness: none }
```

`maximum_height_agl_m` is checked against resolved route/terrain AGL plus
`vertical_contingency_margin_m` and must be covered by the airspace ceiling.
For `initial_1_to_1`, the GRB must be at least this height. Population
assessment expands the route laterally by the operational margin plus GRB.
Step 8 separately calculates the 3-minute maximum-speed adjacent-area distance,
clamped to 5–35 km, and selects operational population/assembly limits. Medium
or high containment requires a reference proving the resulting GRB was fed back
through Step 2. Annex E compliance remains `not_assessed` in every artifact.

- No ground-risk mitigation credit is computed from a declaration or free-text
  evidence field. Applied declarations make the command return invalid input
  with an explicit Annex B evaluator error.
- Tactical air-risk mitigations do not lower residual ARC. The report derives
  the Tactical Mitigation Performance Requirement (TMPR) robustness from the
  residual ARC. A bare tactical-credit claim is rejected because it does not
  contain evidence of TMPR compliance.
- With no applied mitigations in the required `sora` block, the final GRC
  equals the intrinsic GRC and the SAIL is unchanged. Only SORA `2.5` is
  encoded; other versions are rejected instead of silently mixed.
- These remain operator-input-driven figures for a pre-assessment, never an
  authority determination of compliance.

| Flag | Description |
|------|-------------|
| `--format markdown` | SORA report with unmitigated GRC/ARC/SAIL and all Table 14 OSO rows (default) |
| `--format json` | `sora-envelope.v3` JSON with provenance, population evidence, Step 8 requirements, and explicit unassessed-compliance state |

```bash
uv run bvlos-sim sora \
  examples/missions/pipeline_demo_001_ground_risk.yaml \
  examples/vehicles/quadplane_v1_ground_risk.yaml \
  --format markdown
```

Example output excerpt (no mitigations declared):

```text
# SORA Pre-Assessment: pipeline_demo_001_ground_risk

Intrinsic Ground Risk Class (iGRC): 3
Final Ground Risk Class (GRC):      3   (no mitigations applied)
Air Risk Class (ARC):               ARC-b
SAIL:                               II

## Table 14 OSOs at SAIL II

| OSO | Title | Robustness | Required | Operator | Training organisation | Designer | Notes |
|-----|-------|------------|----------|----------|-----------------------|----------|-------|
| OSO#01 | Ensure the operator is competent and/or proven | L | yes | X | - | - | - |
| OSO#02 | UAS manufactured by competent and/or proven entity | NR | no | - | - | X | - |
```

ARC is assigned from the whole-volume airspace descriptor using aerodrome
proximity, controlled status, Mode-C veil/TMZ status, urban/rural setting, and
the 500 ft AGL boundary. `atypical_or_segregated: true` (ARC-a) is rejected until
an authority-backed evidence workflow exists. Likewise,
`entirely_above_flight_level_600: true` is rejected until pressure-altitude
evidence can be assessed. A boolean strategic ARC credit is rejected because
SORA 2.5 requires local encounter-rate evidence.
Tactical mitigation satisfies the TMPR derived from the residual ARC and does
not lower the ARC.

Write a route altitude profile (terrain clearance table):

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format profile
```

The table shows one row per leg with start/end AMSL altitudes, and terrain
elevation and clearance columns when `assets.terrain_file` is configured in
the mission YAML. Without terrain data the Terrain and Clearance columns are
omitted and a note is shown. The same `--format profile` flag works on the
`scenario` command.

Write a pre-flight go/no-go checklist:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format checklist
```

Example output:

```text
## Pre-Flight Checklist: mission

✓ Energy feasibility       PASS   reserve 360.0 Wh above threshold (585.0 Wh at landing, 225.0 Wh threshold)
◌ Geofence clearance       N/A    not evaluated
◌ Landing-zone coverage    N/A    not evaluated
◌ Resource availability    N/A    not evaluated
◌ Link availability        N/A    not evaluated
◌ Obstacle clearance       N/A    not evaluated
◌ Weather limits           N/A    not evaluated
◌ Ground risk class        N/A    not evaluated
  Advisory warnings        4      LOITER_ASSUMED_ZERO_GROUND_DISTANCE, ...

Status: NO-GO
```

`Status: GO` means every required check is present and passed, mission iGRC is
within the supported envelope, RTH reserve holds, and there are no warnings.
`Status: NO-GO` means a check failed or required evidence is missing. Categories
not included in the estimate show `◌  N/A` and therefore prevent `GO`.
The same `--format checklist` flag works on the `scenario` command.

### Energy Reserve Sensitivity

Use `estimate --format sensitivity` to run a deterministic reserve sweep around
one mission and vehicle. The report varies cruise power, uniform east-component
headwind, and battery capacity around the baseline estimate, then marks the
mission `ROBUST` when every variation remains feasible.

| Flag | Default | Description |
|------|---------|-------------|
| `--sensitivity-power-steps` | `10,20,30` | Cruise-power percent deltas to test in both directions |
| `--sensitivity-wind-steps` | `1,2,3` | Headwind m/s deltas to test in both directions |
| `--sensitivity-battery-steps` | `10,20,30` | Battery-capacity percent deltas to test in both directions |

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format sensitivity
```

Example output excerpt:

```text
# Energy Reserve Sensitivity: pipeline_demo_001

Status: ROBUST - all variations remain FEASIBLE with positive reserve
Baseline reserve: 858.5 Wh (95.4%)

## Cruise Power Variation
| Variation | Reserve Wh | Reserve % | Status |
|-----------|------------|-----------|--------|
| -30% | 861.6 | 95.7 | FEASIBLE |
| baseline | 858.5 | 95.4 | FEASIBLE |
| +30% | 855.4 | 95.0 | FEASIBLE |
```

### Minimum Battery Sizing

Use `size-battery` to search for the smallest battery capacity that makes a
mission feasible under the same deterministic estimator used by `estimate`.
The command exits `0` when sizing succeeds whether the current vehicle battery
is already sufficient or needs to be increased.

Sizing includes the candidate pack's mass and refuses to assume a massless
capacity change. The vehicle must define
`energy.battery_excluded_operating_mass_kg` and
`energy.battery_specific_energy_wh_per_kg`. Phase powers are treated as
calibrated at the profile's current pack mass unless `energy.reference_mass_kg`
is explicit. The search stops at `mass.max_takeoff_kg` if no feasible pack fits
within MTOW. It does not assume that feasibility improves monotonically with
capacity: superlinear induced-power growth can make a heavier pack infeasible
again. The report therefore includes the first verified feasible interval and
its 1 Wh search resolution.

Requested percentage margins are checked against that interval. A target above
the verified upper bound is reported as `UNAVAILABLE`; JSON uses
`recommended_capacity_wh: null` plus `unavailable_reason`. Never substitute the
upper bound silently, and do not interpret a recommendation as permission to
use an arbitrarily larger pack. Non-capacity blockers such as geofence, weather,
or link failures stop sizing with the original failure code. The reported
`mission_energy_wh` and `reserve_threshold_wh` are evaluated at the minimum
feasible pack; fields prefixed with `current_` describe the input pack.

| Flag | Default | Description |
|------|---------|-------------|
| `--format` | `markdown` | Output format: `markdown`, `json`, or `summary` |
| `--margin` | `10`, `20`, `30` | Safety margin percent to recommend; repeat for multiple margins |
| `--output`, `-o` | stdout | Write the report to a file |

```bash
uv run bvlos-sim size-battery \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery_sizing.yaml \
  --margin 20
```

Example output excerpt:

```text
## Battery Sizing: alpine_infeasible_001

Mission energy required:   69.2 Wh
Reserve threshold (25 %):  21.2 Wh (of battery capacity)

Minimum feasible capacity: 127.6 Wh
Maximum feasible capacity: 900.0 Wh
Search resolution: 1.0 Wh
With 20 % safety margin:      153.1 Wh

Recommendation: target 153.1 Wh (20 % margin); do not exceed the verified 900.0 Wh upper bound.

Status: SIZED
```

Write the versioned JSON envelope instead:

```bash
uv run bvlos-sim size-battery mission.yaml vehicle.yaml --format json
```

### Energy Reserve Explained

The `reserve` field in `--format summary` output is the margin above (positive) or
below (negative) the reserve threshold, as a percentage of the threshold:

```
reserve_margin_% = (reserve_at_landing_wh / reserve_threshold_wh - 1) × 100
```

The reserve threshold is set in Wh and derived from a percent of battery capacity:

```
reserve_threshold_wh = battery_capacity_wh × reserve_threshold_percent / 100
```

The percent used is `mission.constraints.min_landing_reserve_percent` when set;
otherwise it falls back to `vehicle.energy.reserve_percent_default`. Set one or
both to control how much energy must remain at landing for the mission to be
considered feasible.

```yaml
# mission.yaml
constraints:
  min_landing_reserve_percent: 25.0   # 25% of battery capacity must survive landing

# vehicle.yaml
energy:
  battery_capacity_wh: 900.0
  reserve_percent_default: 20.0       # used if mission doesn't override
```

A `reserve 281.6 %` summary means landing energy was 281.6% above the threshold
(i.e., 3.8× the required reserve remained). A `reserve −12.4 %` means landing
energy was 12.4% below the threshold and the mission is `INFEASIBLE`.

### Energy-Model Fidelity

Vehicle profiles can opt into deterministic mass, air-density, and usable
state-of-charge adjustments while keeping the existing phase-power fields as
the calibration anchor:

```yaml
mass:
  empty_kg: 8.0
  max_payload_kg: 2.0
  max_takeoff_kg: 12.0
  operating_mass_kg: 11.0

energy:
  battery_capacity_wh: 900.0
  reserve_percent_default: 25.0
  cruise_power_w: 450.0
  hover_power_w: 1200.0
  climb_power_w: 1500.0
  reference_mass_kg: 10.0
  reference_density_kgm3: 1.225
  induced_power_mass_exponent: 1.5
  usable_capacity_curve:
    - {soc: 0.0, usable_fraction: 0.0}
    - {soc: 1.0, usable_fraction: 0.9}
```

When `operating_mass_kg` and `reference_mass_kg` are both present, hover and
climb power scale with the configured induced-power exponent. Cruise-like legs
use a milder mass exponent. Any leg with positive or negative vertical motion
uses the configured climb or descent power respectively. When
`reference_density_kgm3` is present, induced-power phases scale by the square
root of the reference-to-actual ISA density ratio. Cruise-like phases use the
larger of that ratio and its inverse, so extrapolation away from the calibration
density is conservative in either direction. The usable-capacity curve derates
`result.energy.usable_energy_wh`; it does not lower the reserve threshold.

Markdown reports include a per-leg mass/density factor table when any factor is
active. Treat these closed-form scalings as a pre-calibration aid, not a
substitute for aircraft-specific log calibration.

## Validation Against Real Flights

Use `validate` to compare a predicted mission estimate against an observed flight
trace:

```bash
uv run bvlos-sim validate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  examples/flight_logs/pipeline_demo_001_trace.json
```

The command loads the mission and vehicle (resolving the same terrain, wind,
geofence, landing-zone, obstacle, and population assets as `estimate`), runs the
estimator, loads a `flight-trace.v1` JSON file (produced by flight-log
ingestion), segments it into flight phases, and reports predicted-vs-observed
metrics at mission and per-phase level. Per-phase comparison lines predicted legs
up with observed trace segments on their shared estimator leg-phase.

Mission metrics: total flight time, total horizontal distance (WGS-84 geodesic
over trace records), mean groundspeed, and reserve at landing (estimator reserve
% vs the trace's final battery-remaining %). Each metric carries `predicted`,
`observed`, `abs_error`, and `pct_error`. Observed phases with no estimator
counterpart (climb, descent, divert, unknown) and missing observed fields are
reported in `notes`.

Install the optional readers, then normalize an ArduPilot DataFlash text/binary
log or PX4 ULog. Supplying the paired inputs embeds their content hashes, which
`validate` requires and verifies before comparing results:

```bash
uv sync --extra flight-logs
uv run bvlos-sim ingest-log flight.bin \
  --trace-id my-flight-001 \
  --mission mission.yaml \
  --vehicle vehicle.yaml \
  --output my-flight-001_trace.json
```

Ingestion snapshots the source bytes before parsing to prevent path races. The
default and hard process-safety ceiling is 64 MiB because text decoding and the
binary reader libraries allocate additional in-memory structures. Use
`--max-size-mib` only to lower that ceiling; split larger logs before ingestion.

The public Python dispatch detects the format from file content:

```python
from pathlib import Path
from adapters.flight_log import ingest_flight_log, write_flight_trace

trace = ingest_flight_log(Path("flight.bin"), trace_id="my-flight-001")
write_flight_trace(trace, Path("my-flight-001_trace.json"))
```

Binary readers are library-backed (`pymavlink` and `pyulog`) and isolated in the
`flight-logs` extra. Unknown formats and logs over the bounded size limit fail
before parsing.

| Flag | Default | Description |
|------|---------|-------------|
| `--validation-id` | `<trace_id>-validation` | Stable report identifier |
| `--format` | `markdown` | `markdown` report or `json` (`validation-report.v2` envelope) |
| `--output`, `-o` | stdout | Write the report to a file |
| `--max-time-error-percent` | `20` | Maximum mission-time error |
| `--max-distance-error-percent` | `10` | Maximum horizontal-distance error |
| `--max-speed-error-percent` | `15` | Maximum mean-groundspeed error |
| `--max-reserve-error-percent` | `10` | Maximum landing-reserve error |

Every gated metric must be present and within its threshold. A failed acceptance
gate still writes the report and exits `10`; a trace whose mission/vehicle hashes
do not match the supplied inputs is rejected as invalid input (`11`).

## Calibration

Where `validate` *measures* where the model drifts on your aircraft, `calibrate`
*closes the gap*: it fits a narrow set of vehicle performance parameters from one
or more observed flights and emits a versioned, deterministic
`calibration-profile.v1` artifact that layers on the base vehicle.

```bash
uv run bvlos-sim calibrate \
  examples/vehicles/quadplane_v1.yaml \
  examples/flight_logs/pipeline_demo_001_trace.json
```

The command loads the base vehicle and one or more `flight-trace.v1` JSON files
(from flight-log ingestion), segments each trace into flight phases, and fits:

- `cruise_speed_mps` — mean true airspeed reconstructed from ground-velocity
  and wind vectors over transit-phase records,
- `climb_rate_mps` / `descent_rate_mps` — mean vertical rate over climbing /
  descending records,
- `max_station_keep_wind_mps` — the strongest wind held against during loiter
  dwell.

Each fitted record carries the value, the observed range, the sample spread,
the sample count, the applicable conditions, and provenance (source trace IDs,
tool version, dataset version). Parameters with no supporting samples are listed
in `notes`, never fabricated. Energy coefficients are not yet fit. The fit is
deterministic: identical inputs produce byte-identical canonical JSON.

| Flag | Default | Description |
|------|---------|-------------|
| `--calibration-id` | `<vehicle_id>-calibration` | Stable artifact identifier |
| `--format` | `markdown` | `markdown` report or `json` (`calibration-profile.v1` envelope) |
| `--output`, `-o` | stdout | Write the artifact to a file |

### Running calibrated

A calibration artifact is opt-in everywhere via `--calibration PATH`: it overrides
only the fitted vehicle fields and never changes behaviour when absent. The
artifact's `base_vehicle_id` must match the vehicle's `vehicle_id` (a mismatch is
rejected as invalid input).

```bash
# Estimate, scenario, and validate all accept --calibration
uv run bvlos-sim estimate mission.yaml vehicle.yaml --calibration cal.json
uv run bvlos-sim scenario scenario.yaml --calibration cal.json
uv run bvlos-sim validate mission.yaml vehicle.yaml trace.json --calibration cal.json
```

See `examples/calibration/` for a full ingestion → segmentation → fitting →
apply walkthrough.

## Contract Discovery (`schema-versions`)

`schema-versions` (alias `contracts`) prints the supported input and output
contract versions plus the resolved `tool_version` as canonical JSON, then exits
`0` without loading any mission, vehicle, or asset file. A backend can call it at
startup to pin and check contract compatibility instead of running a full job to
read the versions off an envelope.

```bash
uv run bvlos-sim schema-versions
# alias:
uv run bvlos-sim contracts
```

Sample output (versions sourced from the same constants the envelopes emit, so
they cannot drift from a real run):

```json
{
  "input_schemas": {
    "batch": "batch.v1",
    "geofences": "geofence-geojson.v1",
    "landing_zones": "landing-zone-geojson.v1",
    "mission": "mission.v7",
    "population": "population-grid.v1",
    "scenario": "scenario.v1",
    "stochastic": "stochastic.v2",
    "terrain": "terrain-grid.v1",
    "uncertainty": "uncertainty.v2",
    "vehicle": "vehicle.v4",
    "wind_grid": "wind-grid.v1"
  },
  "output_envelopes": {
    "battery_sizing_report": "battery-sizing-report.v2",
    "calibration_profile": "calibration-profile.v1",
    "estimator": "estimator-envelope.v9",
    "flight_trace": "flight-trace.v1",
    "phase_segments": "phase-segments.v1",
    "scenario_report": "scenario-report.v3",
    "sitl_comparison": "sitl-comparison.v1",
    "sitl_evidence": "sitl-evidence.v1",
    "sora_assessment": "sora-assessment.v3",
    "sora_envelope": "sora-envelope.v3",
    "stochastic_envelope": "stochastic-envelope.v2",
    "uncertainty_report": "uncertainty-report.v2",
    "validation_report": "validation-report.v2"
  },
  "tool_version": "0.32.0"
}
```

The command is read-only and always exits `0`; `--version` is unchanged and
still prints the plain `bvlos-sim <version>` line.

## Releasing (`bump`)

Cut a release in one reviewed step. `bump` bumps the version and rolls the
changelog; it never tags, pushes, or publishes.

```bash
# preview the next version and the exact edits, writing nothing
uv run bvlos-sim bump patch --dry-run

# apply: update pyproject.toml and roll CHANGELOG.md ([Unreleased] -> dated section)
uv run bvlos-sim bump minor
```

After `bump` applies the edits it prints the suggested follow-up commands:

```bash
git commit -am 'chore: release vX.Y.Z'
git tag vX.Y.Z
git push && git push origin vX.Y.Z
```

`--check` verifies the version sources agree and is meant for CI — it exits
non-zero when `pyproject.toml` is behind the latest `v*` git tag (the drift that
shipped a mismatched `v0.32.0`):

```bash
uv run bvlos-sim bump --check
```

Golden fixtures are version-agnostic: tests pin the embedded `tool_version` to
`0.0.0-test` (via the `BVLOS_SIM_TOOL_VERSION` override set in `conftest.py`), so
a bump never rewrites fixtures and a release cannot break the golden suite.

## Vehicle Profiles

Reference and community vehicle profiles live under `examples/vehicles/`.
The starter community set is in `examples/vehicles/community/`:

- `dji_matrice_300_rtk.yaml`
- `wingtra_one_gen2.yaml`
- `qs_trinity_f90_plus.yaml`
- `autel_evo_max_4t.yaml`
- `generic_survey_hexacopter.yaml`

Each profile includes manufacturer-derived or typical-class values plus
`metadata.source` and calibration notes. Before using a community profile with
an existing mission, update `mission.vehicle_profile` to match the profile's
`vehicle_id`; the CLI rejects mismatches to prevent accidental vehicle swaps.
Validate any community profile against observed flight logs before operational
use.

## Scenario Execution

Run the example scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Run the fidelity v2 scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_v2_scenario.yaml
```

Run the integrated scenario that combines fidelity v2, terrain, wind-grid,
geofence, landing-zone, energy, and lost-link policy checks:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml
```

Run the integrated resource/link scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_resource_link_scenario.yaml
```

Write Markdown:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format markdown \
  --output /tmp/scenario-report.md
```

Write a one-line summary:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format summary
```

Example output:

```text
PASSED 3/3   reserve 281.6 %   flight 2m 49s   warnings 4
```

`PASSED` describes scenario assertions, not operational readiness. With the
warnings shown above (or any missing readiness evidence), the default process
still exits `10`; `scenario-report.v3.operational_readiness` gives the reason.
Use `--engineering-only` only when assertion pass/fail should be the shell
criterion for a non-operational workflow.

The `policy <ACTION>` field appears only when a lost-link event fires and a
policy action is selected (e.g. `policy DIVERT`, `policy RTL`). The `warnings N`
field appears only when the estimate has advisory warnings.

Write GeoJSON route layers from the scenario estimate:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format geojson \
  --output /tmp/scenario-route.geojson
```

Write KML route layers from the scenario estimate:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format kml \
  --output /tmp/scenario-route.kml
```

### Scenario Exit Codes

- `0`: scenario passed
- `10`: scenario failed
- `11`: invalid input
- `13`: internal error

Skipped or unsupported assertions do not fail the scenario unless another
assertion fails.

### Scenario Events

Supported event kinds:

- `observe`: records that a timeline trigger fired
- `lost_link`: records link-loss timing and evaluates `lost_link_policy` when configured
- `wind_change`: changes the active wind from the trigger time onward
- `landing_zone_unavailable`: marks one or more landing zones as unavailable from this point in the timeline onward

All events require `event_id` (slug pattern `[a-z0-9][a-z0-9-]*`) and a `trigger` field.
An optional `description` string may be added to any event or assertion for human-readable
documentation — it is stored in the schema but not interpreted by the runner.

Supported triggers:

| Trigger | Extra field required |
|---------|----------------------|
| `at_mission_start` | — |
| `at_route_item` | `trigger_route_item_id` |
| `at_elapsed_time` | `trigger_elapsed_time_s` |
| `at_mission_end` | — |

When a trigger cannot be resolved (e.g. `trigger_route_item_id` not found in the timeline,
`trigger_elapsed_time_s` exceeds mission duration), the event is marked `fired: false` and the
`event_outcome.not_fired_reason` field in the JSON envelope contains a human-readable explanation
— useful for debugging scenario YAML without re-running in verbose mode.

`landing_zone_unavailable` events require `unavailable_zone_ids` (a list of zone IDs from the
landing-zone GeoJSON). When a zone is marked unavailable, reachability is re-evaluated from
that route item onward. Any previously reachable zone that is now unavailable causes an
infeasibility if no other zone remains reachable:

```yaml
events:
  - event_id: lz-closed
    kind: landing_zone_unavailable
    trigger: at_route_item
    trigger_route_item_id: wp1
    unavailable_zone_ids:
      - demo_landing_zone_wp1
```

`wind_change` events accept either scalar wind:

```yaml
events:
  - event_id: wind-shift
    kind: wind_change
    trigger: at_elapsed_time
    trigger_elapsed_time_s: 120.0
    wind_east_mps: 4.0
    wind_north_mps: -1.0
```

or altitude-banded wind layers:

```yaml
events:
  - event_id: layered-wind
    kind: wind_change
    trigger: at_route_item
    trigger_route_item_id: wp1
    wind_layers:
      - altitude_m: 0.0
        wind_east_mps: 2.0
        wind_north_mps: 0.0
      - altitude_m: 120.0
        wind_east_mps: 5.0
        wind_north_mps: -1.0
```

### Lost-Link Policy

The `lost_link_policy` block defines what the vehicle does when the `lost_link` event fires.
It can be set in the mission YAML (under `policy.lost_link_policy`) or overridden per scenario
in `initial_conditions.lost_link_policy`. Set `policy.lost_link_policy: standard_lost_link_v1`
in the mission to activate the default RTL-after-loiter policy.

Inline `lost_link_policy` fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | string | required | Contingency action: `rtl`, `land`, `loiter`, or `divert` |
| `loiter_s` | float | `0.0` | Seconds to loiter at the link-loss point before acting |
| `divert_target_id` | string | `null` | Landing zone ID to divert to; required when `action` is `divert` |

Example — loiter 30 s then RTL:

```yaml
initial_conditions:
  lost_link_policy:
    action: rtl
    loiter_s: 30.0
```

Example — divert to a named landing zone immediately:

```yaml
initial_conditions:
  lost_link_policy:
    action: divert
    loiter_s: 0.0
    divert_target_id: demo_landing_zone_wp1
```

#### Per-Event Contingency Policies

A `lost_link` event can define its own `policy` block. When present, that
event-level policy takes precedence over `initial_conditions.lost_link_policy`
for that event only. Events without a `policy` keep using the global policy.

```yaml
initial_conditions:
  lost_link_policy:
    action: rtl
    loiter_s: 30.0
events:
  - event_id: link-loss-mid
    kind: lost_link
    trigger: at_route_item
    trigger_route_item_id: wp1
    policy:
      action: divert
      loiter_s: 0.0
      divert_target_id: demo_landing_zone_wp1
  - event_id: link-loss-late
    kind: lost_link
    trigger: at_route_item
    trigger_route_item_id: loiter
    policy:
      action: land
      loiter_s: 0.0
```

`policy` is valid only on `lost_link` events. Setting it on `observe`,
`wind_change`, or `landing_zone_unavailable` is rejected during scenario schema
validation.

The divert estimate (Dubins path distance, transit time, reserve remaining) is included in the
`scenario-report.v3` envelope under each `event_outcome.policy_outcome.divert_estimate`.

### Scenario Assertions

Assertions run after the estimator completes and test fields on the result envelope or
policy outcomes. Unrecognised or skipped assertions do not fail the scenario; when any
assertions are `unsupported` (unrecognised `field_path` or unsupported kind), the
`--format summary` line includes `[N unsupported]` to alert operators.

| Kind | Required fields | Passes when |
|------|-----------------|-------------|
| `estimate_succeeds` | — | `estimate.status == "success"` |
| `estimate_fails` | — | `estimate.status != "success"` |
| `field_lt` | `field_path`, `expected` | field value `< expected` |
| `field_gt` | `field_path`, `expected` | field value `> expected` |
| `field_le` | `field_path`, `expected` | field value `<= expected` |
| `field_ge` | `field_path`, `expected` | field value `>= expected` |
| `field_eq` | `field_path`, `expected` | field value `== expected` (bool or float) |
| `policy_action_eq` | `event_id`, `expected` | lost-link policy action for the event equals `expected` |
| `policy_divert_feasible` | `event_id` | divert route computed for the event is feasible (reserve ≥ threshold) |

`field_path` uses dot notation against the nested estimate result. All supported paths:

```
estimate.status                              # "success" | "infeasible" | "error"
estimate.total_time_s
estimate.total_horizontal_distance_m
estimate.total_vertical_distance_m
estimate.total_path_distance_m
estimate.totals_are_partial                  # true if estimate was cut short
estimate.energy.is_feasible
estimate.energy.total_energy_wh
estimate.energy.reserve_at_landing_wh
estimate.energy.reserve_at_landing_percent
estimate.energy.reserve_threshold_wh
estimate.energy.reserve_threshold_percent
estimate.geofence.is_feasible
estimate.landing_zone.is_feasible
estimate.resource.is_feasible
estimate.link.is_feasible
estimate.obstacle.is_feasible
estimate.weather.is_feasible
estimate.weather.worst_wind_speed_mps
estimate.ground_risk.mission_igrc
```

Obstacle, weather, and ground-risk paths resolve to `None` (yielding a `skipped`
assertion outcome) when the corresponding block was not evaluated — for
example when the mission sets no obstacle file, no weather minimums, or no
population grid is configured.

An assertion with an unrecognised `field_path` yields `unsupported` outcome; the
`unsupported_reason` field in the JSON result lists all valid paths.

Example assertions block:

```yaml
assertions:
  - assertion_id: estimate-succeeds
    kind: estimate_succeeds
  - assertion_id: reserve-margin-ok
    kind: field_gt
    field_path: estimate.energy.reserve_at_landing_wh
    expected: 100.0
  - assertion_id: policy-is-rtl
    kind: policy_action_eq
    event_id: link-lost
    expected: rtl
```

`expected` for `field_eq` on boolean fields can be written as `true`/`false` (unquoted YAML).

## Monte Carlo Sampling

The `sample` command runs a seeded diagnostic parameter sweep and emits
`uncertainty-report.v2`. Use it to study sensitivity to bounded input
distributions rather than to claim an operational probability.
For long runs it can stream machine-readable progress — see
[Run Progress (JSONL)](#run-progress-jsonl).

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format json \
  --output /tmp/uncertainty.json
```

Write Markdown:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format markdown \
  --output /tmp/uncertainty-report.md
```

Print a one-line summary:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format summary
```

Example output: `DIAGNOSTIC   modeled_pass 100%   conditional_end_energy p5 811.3 Wh   p50 854.9 Wh   p95 898.2 Wh   time p50 2m 50s   n=200`

The `seed` in the uncertainty YAML makes repeated runs reproducible for the same
sample count and distributions. `modeled_constraint_pass_rate` is the fraction
of evaluated samples whose independent deterministic run passed the modeled
constraints; failed executions are excluded from its denominator. It is not an
operational, landing, control, or spatial-coverage probability. Mission-time and
mission-end-energy percentiles are conditional on modeled-pass samples only.

Reading the percentiles: `p5` is the 5th percentile — 95% of modeled-pass
samples landed with at least that much energy, so plan against `p5`, not the
median `p50`. `p95` is the optimistic tail. A wide `p5`–`p95` spread means the
sampled uncertainty (for example wind) dominates the outcome.

### Uncertainty YAML reference

Five parameters can be sampled independently. Unset parameters hold their
deterministic value for every sample.

| Parameter | Overrides | Example range |
|-----------|-----------|---------------|
| `wind_east_mps` | wind East component (m/s) | `mean: 0.0, std: 2.0` |
| `wind_north_mps` | wind North component (m/s) | `mean: 0.0, std: 2.0` |
| `cruise_speed_mps` | `mission.defaults.cruise_speed_mps` | `low: 14.0, high: 22.0` |
| `cruise_power_w` | `vehicle.energy.cruise_power_w` | `low: 400.0, high: 500.0` |
| `battery_capacity_wh` | `vehicle.energy.battery_capacity_wh` | `low: 850.0, high: 950.0` |

Two distribution kinds are supported:

```yaml
# Normal (Gaussian) — wind components only; fields: mean, std (must be > 0)
wind_east_mps:
  kind: normal
  mean: 0.0
  std: 2.0

# Uniform — fields: low (inclusive), high (exclusive)
cruise_speed_mps:
  kind: uniform
  low: 14.0
  high: 22.0
```

`cruise_speed_mps`, `cruise_power_w`, and `battery_capacity_wh` must use
bounded uniform distributions with `low > 0`. Unbounded normal support is
rejected instead of clipping nonphysical draws.

## Stochastic Propagation

The `propagate` command runs a diagnostic, open-loop parameter sweep over the
mission timeline. Each sample is first evaluated independently by the
deterministic estimator, and each passing sample retains its own route timings
and geodesic position curve. It emits `stochastic-envelope.v2`. For long runs it
can stream machine-readable progress — see
[Run Progress (JSONL)](#run-progress-jsonl).

This output is deliberately **not an operational-feasibility or landing
probability**. `operational_feasibility_assessed` is always `false`.
`modeled_constraint_pass_rate` describes only the supplied deterministic model
constraints. Timeline and reserve distributions are conditional on those
modeled-pass samples; infeasible and failed samples are excluded from their
statistics. The timeline field is therefore named
`conditional_reserve_violation_rate` and includes its contributing sample
count.

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format json \
  --output /tmp/stochastic.json
```

Write Markdown:

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format markdown \
  --output /tmp/stochastic-report.md
```

Print a one-line summary:

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format summary
```

Example output: `DIAGNOSTIC   modeled_pass 100%   conditional_reserve p5 822.2 Wh   p50 858.7 Wh   p95 909.1 Wh   time 2m 49s   n=100`

The `seed` in the stochastic YAML makes repeated runs reproducible for the
same sample count and parameters. `reserve_at_mission_end_wh` gives conditional
distribution statistics (mean, sample standard deviation, p5, p50, p95) over
modeled-pass samples.

Sample accounting in the result uses three-way partitioning:
`sample_count + infeasible_sample_count + failed_sample_count == plan.samples`.
`spatial_infeasible_count` is a subset of `infeasible_sample_count`; never add
it to the total a second time.
A `spatial_infeasible_count > 0` means some particles were rejected because the
route was geometrically infeasible for that sample — for example, a sampled
battery capacity too low to afford the divert reserve to any available landing
zone. These are counted as non-passing in `modeled_constraint_pass_rate`. When
`--format summary` is used, non-zero counts appear as extra fields:

```
DIAGNOSTIC   modeled_pass 0%   time 2m 49s   n=0   infeasible=6   spatial_infeasible=6
```

If the mission has no geofence or landing-zone assets, `spatial_infeasible_count`
is always 0.

Sensor-only EKF diagnostics remain available. A vehicle containing a
`controller` block is rejected: the former controller propagation did not
model nominal along-track position, vertical/loiter kinematics, or spatial
constraint re-evaluation. Non-zero process-wind noise is likewise rejected
rather than approximated as passive drift with an arbitrary energy multiplier.

The `stochastic.v2` YAML accepts the same five parameter names as
`uncertainty.v2`. Wind components may use normal or uniform distributions.
Strictly positive physical parameters (`cruise_speed_mps`, `cruise_power_w`,
and `battery_capacity_wh`) must use a bounded uniform distribution whose lower
bound is greater than zero. Values are never clipped to an invented minimum.

```yaml
schema_version: stochastic.v2
propagation_id: my-propagation
mission_file: path/to/mission.yaml
vehicle_file: path/to/vehicle.yaml
dt_s: 2.0                       # time step in seconds
samples: 100                    # number of particles (max 10 000)
seed: 42                        # fixed seed for reproducibility
wind_process_noise_std_mps: 0.0 # only supported value in v2
parameters:
  wind_east_mps:
    kind: normal
    mean: 0.0
    std: 2.0
  wind_north_mps:
    kind: normal
    mean: 0.0
    std: 2.0
  cruise_speed_mps:             # optional — omit to hold at mission default
    kind: uniform
    low: 14.0
    high: 22.0
  cruise_power_w:
    kind: uniform
    low: 400.0
    high: 500.0
  battery_capacity_wh:
    kind: uniform
    low: 850.0
    high: 950.0
```

## Run Progress (JSONL)

The long-running commands `sample`, `propagate`, and `batch` can emit
structured, line-oriented progress so a non-interactive caller (a queue worker)
can show live progress instead of a flat "running" until the process exits. The
feature is **opt-in and off by default**; a run with no progress flag behaves
byte-for-byte as before.

Two flags control it, consistent across all three commands:

- `--progress-format jsonl` — emit JSONL progress to **stderr** (default is
  `none`, which emits nothing).
- `--progress-file PATH` — write the JSONL stream to a file instead of stderr
  (implies `jsonl`). The file is opened for live tailing, not an atomic replace,
  so a worker can follow it as it grows.

```bash
# progress on stderr, result envelope on stdout
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --progress-format jsonl

# progress to a sidecar file, result to --output
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --progress-file /tmp/propagate.progress.jsonl \
  --output /tmp/stochastic.json
```

Each line is one compact JSON object with stable keys:

```json
{"event":"progress","command":"propagate","completed":250,"total":1000,"elapsed_s":75.3}
```

- `completed` increases monotonically and the final record always has
  `completed == total`. For `sample`/`propagate`, `total` is the plan's sample
  count; for `batch`, it is the number of runs in the manifest.
- `elapsed_s` is wall-clock seconds from the start of the run (monotonic clock).
- Records are emitted at an interval (about one record per 5% of the run) plus a
  guaranteed final record.

Progress is a **stderr/sidecar side-channel only**: it never appears in the
`--output` JSON stream, introduces no new schema or envelope version, and does
not change the result envelope, the deterministic results, or the exit code.

## SITL Evidence Contract

The `sitl` command reuses an existing `scenario.v1` file, runs the deterministic
scenario output as expected behavior, and emits a `sitl-evidence.v1` bundle.
By default it is contract-only. Add `--live` to connect to a running ArduPilot
SITL instance, upload the mission, record telemetry, and emit a completed
evidence bundle.

### Contract-Only Evidence

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml \
  --format json \
  --output /tmp/sitl-evidence.json
```

Write a Markdown evidence summary:

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml \
  --format markdown \
  --output /tmp/sitl-evidence.md
```

The no-op contract adapter writes `status: contract_only`, includes mission,
vehicle, scenario, and loaded asset references, embeds the deterministic
scenario report, and leaves telemetry and command-log artifact lists empty for
live adapters to populate.

### Live SITL Evidence

For a running ArduPilot SITL endpoint, `--live` requires an artifact directory.
The directory is created if it does not exist and receives `telemetry.json`,
`command_log.json`, `simulator_log.json`, and `adapter_log.json`.
Live recording emits progress lines to stderr for connection, mission upload,
arming, AUTO execution, verified mission completion, telemetry recording, and
evidence writing; stdout remains JSON-safe unless `--output` is used. A final
item merely becoming current is not accepted as completion: the adapter waits
for MAVLink mission-complete state or a final `MISSION_ITEM_REACHED` event.

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --live \
  --host 127.0.0.1 \
  --port 5770 \
  --artifact-dir /tmp/bvlos-artifacts \
  --telemetry-samples 20 \
  --telemetry-timeout-s 30.0 \
  --mission-timeout-s 300.0 \
  --output /tmp/sitl-evidence.json
```

The bundled pipeline scenario uses a QuadPlane profile, so the example targets
the ArduPlane/QuadPlane launcher on port `5770`. Use port `5760` only with an
ArduCopter-compatible mission and vehicle profile.

### SITL Comparison Reports

`sitl-comparison.v1` reports compare a `sitl-evidence.v1` bundle against the
embedded deterministic scenario report. Render one through `compare` from an
already-written evidence bundle:

If `--comparison-id` is omitted, `compare` generates the identifier as
`<evidence_id>-comparison`.

`compare` requires a completed `sitl-evidence.v1` bundle (produced with
`sitl --live`). Comparing a contract-only bundle (produced without `--live`)
exits 12 with `"summary": "unsupported"` -- this is expected and means no live
artifacts are available to compare against.

```bash
uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --comparison-id pipeline-demo-sitl-comparison \
  --output /tmp/sitl-comparison.json
```

Write Markdown with the same entry point:

```bash
uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --format markdown \
  --output /tmp/sitl-comparison.md
```

`compare` exits `0` only when the summary is `passed`. A `drifted` or `failed`
summary exits `10`, and an `unsupported` summary exits `12`. The JSON or
Markdown report remains the source of detail for which comparison dimension
changed.

Python adapter APIs expose the same report construction:

```python
from adapters.sitl.comparison import build_sitl_comparison_report
from adapters.sitl.comparison import render_sitl_comparison_json
from adapters.sitl.comparison_markdown import render_sitl_comparison_markdown

report = build_sitl_comparison_report(
    comparison_id="pipeline-demo-sitl-comparison",
    bundle=evidence_bundle,
)
json_report = render_sitl_comparison_json(report)
markdown_report = render_sitl_comparison_markdown(report)
```

Reports include deterministic scenario assertions, mission item count,
telemetry record count, heartbeat presence, adapter lifecycle, simulator
lifecycle, and position proximity when `GLOBAL_POSITION_INT` telemetry is
available.

## Resource and Link Feasibility

Resource systems are configured on vehicle YAML, and communication-link systems
are configured on mission YAML. Scenario `initial_conditions.link_systems`
replaces mission link systems for that scenario run. Reports expose
`result.resource` and `result.link`, and scenario assertions can use
`estimate.resource.is_feasible` and `estimate.link.is_feasible`. Existing
battery-only vehicle files do not need changes.

## Estimator Options

Estimator options can be provided through:

- mission `estimation` YAML
- scenario `initial_conditions` YAML
- CLI flags for the `estimate` command
- Python `EstimationOptions`

Runtime options take precedence over mission `estimation` values.

### Fidelity Mode

Fidelity v1 is the default. Fidelity v2 adds turn-arc dynamics and fixed-wing
circular loiter.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2
```

Mission YAML:

```yaml
estimation:
  fidelity: v2
```

Scenario YAML:

```yaml
initial_conditions:
  fidelity: v2
```

Fidelity v2 controls turn arcs and fixed-wing circular loiter only. To sample a
straight transit leg at bounded intervals, independently set
`estimation.max_segment_length_m`, scenario
`initial_conditions.max_segment_length_m`, runtime
`EstimationOptions.max_segment_length_m`, or CLI
`--max-segment-length-m`. This option also works with fidelity v1.

### Constant Wind

Mission YAML:

```yaml
estimation:
  wind_east_mps: 2.0
  wind_north_mps: -1.0
```

Scenario YAML:

```yaml
initial_conditions:
  wind_east_mps: 2.0
  wind_north_mps: -1.0
```

### Layered Wind

Layered wind uses altitude bands. The highest layer whose `altitude_m` is less
than or equal to the query altitude is used. Below all configured layers, the
lowest layer is used.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --wind-layer "0:2.0:0.0" \
  --wind-layer "500:6.0:-1.0" \
  --wind-layer "1500:12.0:-3.0"
```

Mission YAML:

```yaml
estimation:
  wind_layers:
    - altitude_m: 0.0
      wind_east_mps: 2.0
      wind_north_mps: 0.0
    - altitude_m: 500.0
      wind_east_mps: 6.0
      wind_north_mps: -1.0
```

When `wind_layers` is present, scalar `wind_east_mps` and `wind_north_mps` are
accepted but ignored.

### Sub-Segment Sampling

Sub-segment sampling divides each transit leg into deterministic sub-segments
and samples wind at each midpoint.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --max-segment-length-m 500
```

YAML:

```yaml
estimation:
  max_segment_length_m: 500.0
```

Values must be greater than zero.

### Terrain-Referenced Altitude

Route items with `altitude_reference: terrain` resolve their altitude above the
ground elevation at each waypoint position. This requires an offline elevation
grid asset file.

The grid format is a YAML or JSON file with these fields:

```yaml
origin_lat: 51.990
origin_lon: 3.990
step_lat_deg: 0.001
step_lon_deg: 0.001
elevations_m:
  - [10.0, 10.5, 11.0]
  - [10.2, 10.7, 11.1]
  - [10.3, 10.8, 11.2]
```

Reference the grid from the mission file:

```yaml
assets:
  terrain_file: terrain/flat_polder.yaml
```

Set the default altitude reference for the whole route:

```yaml
defaults:
  altitude_reference: terrain
```

Or per route item:

```yaml
route:
  - id: wp1
    action: waypoint
    lat: 52.001
    lon: 4.002
    altitude_m: 120.0
    altitude_reference: terrain
```

When terrain coverage is missing for a route-item position, the estimator
fails with structured diagnostics (`TERRAIN_COVERAGE_MISSING`). When no
terrain file is configured but a terrain reference is used, the estimator
fails with `UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN`.

See `examples/terrain/flat_polder.yaml` for a working example grid.
See `examples/missions/pipeline_demo_001_integrated.yaml` for a mission that
uses the terrain grid together with geofence, landing-zone, wind-grid, and
fidelity-v2 settings.

### Spatiotemporal Wind Grid

A spatiotemporal wind grid provides wind as a deterministic function of elapsed
time, altitude, latitude, and longitude. It uses quadrilinear interpolation
and clamps at domain boundaries.

The grid format is a YAML or JSON file:

```yaml
axes:
  time_s: [0.0, 600.0]
  altitude_m: [0.0, 200.0]
  lat: [51.990, 52.000, 52.010]
  lon: [3.990, 4.000, 4.010]
values:
  # values[time_idx][alt_idx][lat_idx][lon_idx] = [wind_east_mps, wind_north_mps]
  - - - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
      - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
      - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
    - - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
      - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
      - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
  - - - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
      - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
      - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
    - - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
      - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
      - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
```

Each axis must be strictly monotonically increasing with at least 2 entries.

Reference the grid from the mission file:

```yaml
assets:
  wind_grid_file: wind/pipeline_wind_grid.yaml
```

The CLI `--wind-layer` flags take precedence over `wind_grid_file` when both
are present. `wind_grid_file` takes precedence over `estimation.wind_layers`.
Scenario YAML initial wind settings take precedence over a mission wind grid;
when a scenario leaves initial wind unset, the `scenario` command can inherit
the mission's `assets.wind_grid_file`.

See `examples/wind/pipeline_wind_grid.yaml` for a working example grid.

## Advisory Warning Codes

Advisory warnings appear in `estimate`, `scenario`, `sample`, and `propagate` output when the
estimator detects a condition that does not make the mission infeasible but may affect real
operations. The `--format summary` line includes `warnings N` when any are present; the full
JSON envelope lists each warning with its `code`, `message`, and the leg or route item index
where it was raised.

| Code | Raised by | Meaning | Operator action |
|------|-----------|---------|-----------------|
| `MAX_WIND_EXCEEDED` | transit legs | Measured wind speed on a leg exceeds `vehicle.performance.max_wind_mps`. The estimator does not enforce this limit; the energy model still completes. | Review each flagged leg. If the vehicle cannot fly safely at that wind, revise the route or reschedule. |
| `RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD` | post-estimation | Predicted reserve at landing is below the vehicle's `failsafe.low_battery_abort_percent`. The autopilot may trigger an emergency landing before route completion. | Increase battery capacity, reduce distance, or add an intermediate landing. |
| `RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD` | post-estimation | Predicted reserve at landing is below `failsafe.low_battery_warn_percent`. The vehicle will likely trigger a low-battery alert mid-flight. | Add reserve margin or reduce energy consumption. |
| `GEOFENCE_EVALUATED_2D_ONLY` | geofence check | Geofence intersection uses 2D lon/lat horizontal geometry. `floor_m`/`ceiling_m` altitude bounds are checked when declared. | Verify that any altitude-dependent zone uses AMSL metres; AGL-relative per-zone bounds are not modelled. |
| `DEPARTURE_TIME_MISSING` | geofence check | At least one geofence has an activation window, but the mission omits `departure_time`, so the estimator treats time-windowed zones as always active. | Add a UTC mission `departure_time` to evaluate temporary restrictions against the planned flight window. |
| `DIVERT_ENERGY_TAS_ONLY` | scenario divert routing | A scenario divert was requested without a wind-corrected action-point estimate, so its energy uses true airspeed (TAS). The mission landing-zone coverage gate is wind- and altitude-aware and does not emit this warning. | Supply the scenario wind/action-point context used by wind-corrected divert routing, or apply a conservative headwind margin. |
| `POPULATION_DENSITY_DIMENSION_MISSING` | ground-risk pre-assessment | A mission references `assets.population_grid_file`, but the vehicle profile omits `characteristic_dimension_m`, so iGRC cannot be computed. | Add wingspan, rotor blade diameter, or the multicopter's maximum distance between blade tips before using `--format ground-risk`. |
| `GUST_DATA_UNAVAILABLE` | weather minimums | `constraints.max_gust_mps` is set, but the per-leg wind model carries no gust data, so the gust limit is not enforced. | Treat the gust limit as informational; verify gusts against an external forecast until gust data is modelled. |
| `ROUTE_ACTIONS_AFTER_RTL` | route structure check | Route items appear after an RTL action. Those legs are estimated but operationally unreachable — the aircraft returns home before executing them. | Remove the trailing items or re-order the route so RTL is last. |
| `LOITER_RADIUS_IGNORED` | loiter legs | `loiter_radius_m` is set on a loiter item but ignored; the estimator models loiter as a station-keep hold using `max_station_keep_wind_mps` as authority. | Confirm the loiter duration in `loiter_time_s` is correct. Radius will be used in a future fidelity update. |
| `LOITER_ASSUMED_ZERO_GROUND_DISTANCE` | loiter legs | Loiter dwell is modeled as a station-keep hold with zero ground-path distance. The energy model accounts for hover power but not horizontal drift. | Acceptable for pre-flight checks. For precision loiter energy, use fidelity v2 when circular loiter support is added. |
| `LOW_GROUNDSPEED_MARGIN` | transit legs | Computed groundspeed is within 10% of `min_groundspeed_mps`. Wind is strong relative to cruise speed, which may cause navigation issues. | Reduce cruise altitude where wind is weaker, or use a route that avoids the high-wind leg. |
| `HIGH_CRAB_MARGIN` | transit legs | Crab angle is within 10% of `vehicle.performance.max_crab_angle_deg`. The cross-wind component is near the vehicle limit. | Route the mission to reduce cross-wind exposure or verify the vehicle can sustain the required crab angle. |
| `HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY` | loiter / hover legs | `max_station_keep_wind_mps` is not set in the vehicle profile; `hover_speed_mps` is used as a fallback for station-keep wind authority. | Set `performance.max_station_keep_wind_mps` in the vehicle YAML for a more accurate station-keep check. |

Warnings are informational — the estimator still produces a result. They are attached to the
envelope's `warnings` list and counted in the `--format summary` `warnings N` field. When no
warnings are present, the field is omitted.

## Flight Team Workflow

A typical evidence workflow keeps deterministic checks and live SITL artifacts
separate, then compares them explicitly:

```bash
# 1. Pre-flight estimate
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --output /tmp/estimate.json

# 2. Scenario assertions
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --output /tmp/scenario.json

# 3. Monte Carlo bounds
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --output /tmp/uncertainty.json

# 4. Live SITL validation
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --live --host 127.0.0.1 --port 5760 \
  --artifact-dir /tmp/bvlos-artifacts \
  --output /tmp/sitl-evidence.json

uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --comparison-id pipeline-demo-live \
  --output /tmp/sitl-comparison.json
```

For automated pipelines, treat each step independently -- do not short-circuit
on `estimate` infeasibility before running `scenario` and `sample`, since each
command produces independent evidence. A recommended CI pattern:

```bash
uv run bvlos-sim estimate ... --output /tmp/estimate.json
ESTIMATE_EXIT=$?
uv run bvlos-sim scenario ... --output /tmp/scenario.json
SCENARIO_EXIT=$?
uv run bvlos-sim sample ... --output /tmp/uncertainty.json
```

Each command produces independent evidence. `estimate` exit `10` means either
computational infeasibility or operational NO-GO; inspect `result.failure` and
`operational_readiness` to distinguish them. `scenario` exit `10` can mean an
assertion/scenario failure or operational NO-GO. Both are pre-flight stops for
an operational workflow.
`compare` exiting 10 (`drifted`/`failed`) requires reviewing the changed
dimensions; exit 12 (`unsupported`) means the bundle is contract-only and
`sitl --live` must be run first.

Interpret the workflow outputs in order. Without `--engineering-only`, a
successful `estimate` means the deterministic model is feasible **and** its
operational readiness verdict is GO. A scenario must both pass and reach the
same operational GO. Resolve any failed assertion, policy expectation, missing
evidence, or readiness failure before live validation. In `sample`, a low
`modeled_constraint_pass_rate` or weak conditional tail energy identifies model
sensitivity that needs engineering investigation; it is not an operational
probability or go/no-go verdict. For `compare`, `passed` means live SITL artifacts agreed
with the embedded expectations for supported dimensions; `drifted` means review
the changed dimensions, usually mission upload count, telemetry presence,
adapter lifecycle, or position proximity, before treating the run as evidence.

## Python API

Use the package-root imports for stable caller code:

```python
from estimator import EstimationOptions
from estimator import FidelityMode
from estimator import LayeredWindProvider
from estimator import WindLayer
from estimator import estimate_mission_distance_time
```

Layered wind example:

```python
provider = LayeredWindProvider([
    WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
    WindLayer(altitude_m=500.0, wind_east_mps=6.0, wind_north_mps=-1.0),
])

result = estimate_mission_distance_time(
    mission,
    vehicle,
    wind_provider=provider,
    options=EstimationOptions(
        fidelity=FidelityMode.V2,
        max_segment_length_m=500.0,
    ),
)
```

Terrain, wind-grid, geofence, landing-zone, and scenario execution APIs accept
the same provider objects used by the CLI loaders.

Monte Carlo uncertainty example:

See `examples/uncertainty/` for complete uncertainty plan YAML files.

```python
from estimator import run_monte_carlo

mc_result = run_monte_carlo(plan, mission, vehicle)
print(mc_result.modeled_constraint_pass_rate)
print(mc_result.total_time_s.mean)
print(mc_result.total_time_s.p95)
```

Or via the `sample` CLI command:

```bash
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml --format markdown
```

## Output Contracts

The estimator CLI emits `estimator-envelope.v9`.

It includes a required `operational_readiness` object. The same fail-closed
verdict controls the default exit status for every estimator output format.

The battery sizing CLI emits `battery-sizing-report.v2` when `--format json` is used.
It includes the verified feasible capacity interval, search resolution, and
fail-closed margin recommendations.

The scenario CLI emits `scenario-report.v3`.

It also includes `operational_readiness`; a non-passed scenario adds the
scenario itself to the failed checks. The verdict controls the default exit
status for every scenario output format.

The sample CLI emits diagnostic `uncertainty-report.v2`.

The propagate CLI emits diagnostic `stochastic-envelope.v2`; it explicitly
does not assess operational feasibility.

The SITL contract command emits `sitl-evidence.v1`.

The compare CLI and SITL comparison API emit `sitl-comparison.v1`.

Estimator, scenario, and stochastic JSON outputs are canonical and
regression-tested with golden fixtures. Stochastic output is deterministic
for a fixed seed. Markdown output is supported for human-readable estimator,
scenario, uncertainty, stochastic, and SITL comparison reports.
`estimate --format summary`, `scenario --format summary`,
`sample --format summary`, and `propagate --format summary` emit one-line
plain-text summaries for terminal checks and shell pipelines; no summary
schema or envelope is created. `estimate --format geojson|kml` and
`scenario --format geojson|kml` emit map exports directly from the computed
mission estimate instead of creating a new schema or envelope. Invalid-input
and internal-error paths still fall back to JSON envelopes so automation can
parse failures consistently.

## Verification

```bash
uv run ruff check .
uv run pytest
uv run pytest tests/test_cli.py tests/test_scenario_cli.py  # CLI subset
```
