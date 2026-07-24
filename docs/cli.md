# CLI reference

Exact facts for every command: usage, key flags, output formats, and exit
codes. For a guided first run, see [Getting started](getting-started.md); for
authoring the YAML inputs, see [Missions and vehicles](missions.md).

All commands run as `uv run bvlos-sim <command>` from a source checkout, or
`bvlos-sim <command>` from an installed wheel. Input files may be `.yaml`,
`.yml`, or `.json`; relative asset paths resolve from the referencing file's
directory. Every mission file must declare `schema_version: mission.v7` —
upgrade older files with [`migrate`](#migrate).

## Exit codes

| Code | Meaning |
|-----:|---------|
| `0`  | Success (for `estimate`/`scenario`/`batch`: operational GO, or engineering-only pass) |
| `10` | Infeasible, failed, or operational NO-GO |
| `11` | Invalid input |
| `12` | Unsupported operation |
| `13` | Internal or adapter runtime error |
| `14` | Cancelled by `SIGINT`/`SIGTERM` (console entrypoint only) |

A missing or unreadable input file is invalid input (`11`, with an error
envelope) like any other load failure. Only genuine command-line usage errors
— an unknown flag or a missing required argument — exit `2` from the argument
parser.

Per-command behavior:

| Command | `0` | `10` | `11` | `12` | `13` | Notes |
| -------------- | :-: | :--: | :--: | :--: | :--: | ----- |
| `estimate`     |  ✓  |  ✓   |  ✓   |  ✓   |  ✓   | `11` can also be a *computed* invalid-input failure. |
| `scenario`     |  ✓  |  ✓   |  ✓   |      |  ✓   | Every non-passed outcome collapses to `10`. |
| `batch`        |  ✓  |  ✓   |  ✓   |      |  ✓   | `10` if any run is infeasible or NO-GO; `11` if any run fails to load. |
| `sample`       |  ✓  |      |  ✓   |      |  ✓   | Never `10`: an infeasible Monte Carlo result is in the body, exit `0`. |
| `propagate`    |  ✓  |      |  ✓   |      |  ✓   | Never `10`: same divergence as `sample`. |
| `size-battery` |  ✓  |      |  ✓   |      |  ✓   | A NO answer (no feasible capacity) is in the body, not `10`. |
| `sora`         |  ✓  |  ✓   |  ✓   |  ✓   |  ✓   | `10` for out-of-scope Step 8, GRC > 7, rejected mitigation credit, or an infeasible mission; `12` for an unsupported estimator failure. |
| `validate`     |  ✓  |  ✓   |  ✓   |      |  ✓   | `10` when an acceptance threshold fails. |
| `calibrate`    |  ✓  |      |  ✓   |      |  ✓   | Fitted profile is in the body. |
| `compare`      |  ✓  |  ✓   |  ✓   |  ✓   |  ✓   | `10` drifted/failed; `12` for a contract-only bundle. |
| `convert`      |  ✓  |      |  ✓   |  ✓   |  ✓   | Missing `--vehicle-profile` and parse errors are `11`; a lossy conversion without `--allow-lossy` is `12`. |
| `migrate`      |  ✓  |      |  ✓   |      |      | Legacy input that cannot be migrated is `11`. |
| `export`       |  ✓  |      |  ✓   |      |  ✓   | Mission load / exportability failures are `11`. |
| `ingest-log`   |  ✓  |      |  ✓   |      |  ✓   | Unknown/oversized logs and missing readers are `11`. |
| `sitl`         |  ✓  |      |  ✓   |      |  ✓   | Input failures are `11`; live adapter/timeout failures are `13`. |
| `verify`       |  ✓  |  ✓   |  ✓   |      |  ✓   | `10` on any checksum mismatch or missing artifact; `11` for an unreadable or invalid bundle. |
| `schema-versions` | ✓ |     |      |      |      | Read-only; always `0`. |
| `bump`         |  ✓  |      |  ✓   |      |  ✓   | Developer-only release tool; `11` on version drift. |

Two rules hold everywhere:

- **The exit verdict never depends on the output format.** `estimate`,
  `scenario`, and `batch` apply the fail-closed operational readiness gate for
  JSON, Markdown, summary, checklist, profile, sensitivity, GeoJSON, KML, and
  CSV alike. `--engineering-only` opts out of the gate for non-operational
  analysis; the JSON envelope still records the structured
  `operational_readiness` verdict.
- **`--output` writes are atomic** (temp file, then `os.replace`). An
  interrupted run never leaves a truncated file.

### Preflight validation

`estimate`, `scenario`, `sample`, `propagate`, `batch`, `sora`, `convert`,
`export`, `calibrate`, `compare` and `size-battery` support
`--validate-only`: load and schema-check all inputs — including referenced
mission assets — and exit without running anything. Exit `0` on success,
`11` otherwise. `ingest-log`, `migrate`, `verify-evidence` and `sitl` do
not offer it.

```bash
uv run bvlos-sim estimate mission.yaml vehicle.yaml --validate-only
# mission: mission.yaml: OK
# vehicle: vehicle.yaml: OK
```

Add `--validate-format json` for a machine-readable
`preflight-validation.v1` envelope with one entry per file; a failure pins the
offending file with a stable `stage` (`schema`, `asset-load`, `reference`) and
error `code`.

## estimate

Deterministic mission estimation and static feasibility checks.

**Usage:** `bvlos-sim estimate MISSION VEHICLE [--format FMT] [--output PATH]`

| Flag | Default | Description |
|------|---------|-------------|
| `--format` | `json` | `json`, `markdown`, `summary`, `checklist`, `profile`, `sensitivity`, `ground-risk`, `geojson`, `kml` |
| `--output`, `-o` | stdout | Write the artifact to a file |
| `--engineering-only` | off | Exit `0` on computational feasibility despite missing operational evidence |
| `--fidelity` | `v1` | `v2` adds turn arcs and fixed-wing circular loiter |
| `--wind-layer` | — | `ALT:EAST:NORTH` altitude-banded wind; repeatable |
| `--max-segment-length-m` | — | Sample straight legs at bounded intervals (works in v1 and v2) |
| `--calibration` | — | Apply a `calibration-profile.v1` artifact |

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --format checklist
```

Formats:

- `json` — canonical `estimator-envelope.v10`: provenance, diagnostics, route
  legs, totals, energy/geofence/landing-zone/resource/link/obstacle/weather/
  ground-risk blocks, RTH reserve timeline, and `operational_readiness`.
- `markdown` — human-readable report of the same result.
- `summary` — one line: `FEASIBLE   reserve 279.8 %   flight 2m 49s
  [warnings N] [FAILURE_CODE]`. `reserve` is the margin above (positive) or
  below (negative) the reserve threshold, as a percentage of that threshold —
  not battery state of charge.
- `checklist` — the pre-flight go/no-go view: one `✓`/`✗`/`◌` row per check,
  `Status: GO` or `Status: NO-GO`, and a `Blocked by:` line naming the missing
  evidence, failed checks, or blocking warnings. `GO` requires every check
  present and passed and no unacknowledged warnings (see
  [Advisory warnings](#advisory-warnings)); missing evidence (`◌ N/A`) is
  NO-GO, never an implicit pass.
- `profile` — per-leg altitude table with terrain elevation and clearance
  columns when a terrain asset is configured.
- `sensitivity` — deterministic reserve sweep over cruise power
  (`--sensitivity-power-steps`, default `10,20,30` percent), headwind
  (`--sensitivity-wind-steps`, default `1,2,3` m/s), and battery capacity
  (`--sensitivity-battery-steps`, default `10,20,30` percent); `ROBUST` when
  every variation stays feasible.
- `ground-risk` — SORA iGRC table (mission and per-leg) from a population grid
  and the vehicle's `characteristic_dimension_m` and `max_speed_mps`. This is
  the *intrinsic* class only; the [`sora`](#sora) command adds ARC, SAIL, and
  OSOs.
- `geojson` / `kml` — map-ready route layers (see
  [Map exports](#map-exports)).

## scenario

Deterministic scenario events (lost link, wind change, landing zone
unavailable) and machine-readable assertions over the resulting estimate.

**Usage:** `bvlos-sim scenario SCENARIO [--format FMT] [--output PATH]`

Formats: `json` (`scenario-report.v3`), `markdown`, `summary`, `checklist`,
`profile`, `geojson`, `kml`. Also accepts `--engineering-only` and
`--calibration`.

```bash
uv run bvlos-sim scenario examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format summary
# PASSED 3/3   reserve 279.8 %   flight 2m 49s   warnings 3
```

`PASSED n/total` counts assertions; `policy <ACTION>` appears when a lost-link
event fired. `PASSED` describes assertions, not operational readiness — with
warnings or missing evidence the process still exits `10` unless
`--engineering-only` is set. Scenario YAML structure (events, triggers,
assertions, lost-link policies) is documented in
[Missions and vehicles](missions.md#scenarios-scenariov1).

## batch

Multiple estimate, scenario, or propagate runs from one `batch.v1` manifest.

**Usage:** `bvlos-sim batch MANIFEST [--output-dir DIR] [--format FMT]`

```yaml
format_version: "batch.v1"
runs:
  - id: alpine_standard
    mission: ../real_world/alpine_mission.yaml
    vehicle: ../real_world/quadplane_v1.yaml
```

`run_type` selects what every run in the manifest does — `estimate` (the
default, and what an unversioned manifest means), `scenario`, or `propagate`:

```yaml
format_version: "batch.v1"
run_type: scenario           # each run points at a scenario file
runs:
  - {id: nominal, scenario: scenarios/nominal.yaml}
  - {id: lost_link, scenario: scenarios/lost_link.yaml}
```

```yaml
format_version: "batch.v1"
run_type: propagate          # each run points at a stochastic plan
runs:
  - {id: wind_sweep, plan: stochastic/wind.yaml}
```

Paths resolve relative to the manifest. The table columns match the run type:
estimate shows reserve margin and flight time; scenario shows the assertion
count (`passed/total`); propagate shows the modeled pass rate. Exit is `10`
when any estimate run is infeasible/NO-GO or any scenario run fails; propagate
runs are diagnostic and never exit `10`.

`--output-dir` writes one file per run id, in that run type's envelope
(`estimator-envelope.v10`, `scenario-report.v3`, or `stochastic-envelope.v2`).
`--format` selects `json`, `markdown`, or `summary` for any run type; the
route-shaped formats `geojson`, `kml`, `checklist`, and `profile` are
estimate-only. `--format csv` emits a comma-separated table to stdout, with
columns matching the run type.

## sample

Seeded Monte Carlo parameter sweep over wind, cruise speed, cruise power, and
battery capacity. Emits `uncertainty-report.v2`.

**Usage:** `bvlos-sim sample UNCERTAINTY [--format json|markdown|summary]`

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml --format summary
# DIAGNOSTIC   modeled_pass 100%   conditional_end_energy p5 811.3 Wh   p50 854.9 Wh   p95 898.2 Wh   time p50 2m 50s   n=200
```

This is a diagnostic, not a probability: `modeled_pass` is the fraction of
evaluated samples whose deterministic run passed the modeled constraints, and
the percentiles are conditional on those passing samples. Read `p5` as the
pessimistic tail — 95% of modeled-pass samples land with at least that much
energy — and plan against it, not the median. The command always exits `0`
once the run completes.

## propagate

Time-stepped stochastic particle propagation over the mission timeline, with
optional GPS/battery sensor models and EKF estimation-error traces. Emits
`stochastic-envelope.v2`. Same formats and diagnostic semantics as `sample`;
the timeline adds a per-step `conditional_reserve_violation_rate`.

Sample accounting is three-way: `sample_count + infeasible_sample_count +
failed_sample_count == plan.samples`, and `spatial_infeasible_count` is a
subset of the infeasible count. Vehicles with a `controller` block and
non-zero `wind_process_noise_std_mps` are rejected rather than approximated.

Long `sample`, `propagate`, and `batch` runs can stream progress:
`--progress-format jsonl` emits one JSON object per ~5% of the run to stderr
(`{"event":"progress","command":"propagate","completed":250,"total":1000,"elapsed_s":75.3}`;
batch records also carry `run_id` — the id of the run that just completed —
so a worker can attribute stalls);
`--progress-file PATH` writes the same stream to a tailable file. Progress
never touches the result envelope or the exit code.

## size-battery

Search the minimum battery capacity that makes the mission feasible, including
the candidate pack's mass. The vehicle must define
`energy.battery_excluded_operating_mass_kg` and
`energy.battery_specific_energy_wh_per_kg`.

**Usage:** `bvlos-sim size-battery MISSION VEHICLE [--margin N]... [--format FMT]`

The search stops at `mass.max_takeoff_kg` and does not assume feasibility
improves monotonically with capacity — heavier packs can become infeasible
again — so the report gives a *verified feasible interval* at 1 Wh resolution.
A `--margin` target above the verified upper bound is reported `UNAVAILABLE`,
never silently substituted. Formats: `markdown` (default), `json`
(`battery-sizing-report.v2`), `summary`.

## sora

SORA 2.5 pre-assessment: intrinsic and final GRC, ARC, SAIL, Step 8
adjacent-area and containment requirements, and all 17 Table 14 OSO rows.

**Usage:** `bvlos-sim sora MISSION VEHICLE [--format markdown|json]`

The command is strictly evidence-gated: it requires `population-grid.v2`
population evidence, a complete `airspace` descriptor, and an explicit
`sora.ground_risk_footprint` (see
[Missions and vehicles](missions.md#sora-evidence)). Applied M1/M2 mitigation
declarations earn no credit until an Annex B criteria evaluator exists — the
assessment is still produced with the final GRC equal to the intrinsic GRC,
each declaration is recorded as `credit_rejected_pending_annex_b`, and the
command exits `10` so the no-credit result stays auditable. It never assesses
Annex E containment or OSO compliance and is a planning aid, not an
authorization.

## validate

Compare a predicted mission estimate against an observed flight trace
(`flight-trace.v1`, produced by [`ingest-log`](#ingest-log)).

**Usage:** `bvlos-sim validate MISSION VEHICLE TRACE [--format markdown|json]`

Reports predicted-vs-observed flight time, horizontal distance, mean
groundspeed, and landing reserve at mission and per-phase level, each with
absolute and percent error. Acceptance thresholds gate the exit code:

| Flag | Default | Gates |
|------|---------|-------|
| `--max-time-error-percent` | `20` | Mission-time error |
| `--max-distance-error-percent` | `10` | Horizontal-distance error |
| `--max-speed-error-percent` | `15` | Mean-groundspeed error |
| `--max-reserve-error-percent` | `10` | Landing-reserve error |

A failed gate still writes the report and exits `10`. A trace whose embedded
mission/vehicle hashes do not match the supplied inputs is rejected (`11`).

## calibrate

Fit a calibration profile from observed flights: `cruise_speed_mps`,
`climb_rate_mps`, `descent_rate_mps`, and `max_station_keep_wind_mps`, each
with observed range, spread, sample count, and provenance. Energy coefficients
are not yet fit; parameters with no supporting samples are listed in `notes`,
never fabricated.

**Usage:** `bvlos-sim calibrate VEHICLE TRACE... [--format markdown|json]`

Apply the resulting `calibration-profile.v1` artifact anywhere with
`--calibration PATH` (`estimate`, `scenario`, `validate`). It overrides only
the fitted fields, and its `base_vehicle_id` must match the vehicle.

## ingest-log

Normalize an ArduPilot DataFlash text/binary log or PX4 ULog into
`flight-trace.v1`. Requires the optional readers:

```bash
uv sync --extra flight-logs
uv run bvlos-sim ingest-log flight.bin \
  --trace-id my-flight-001 \
  --mission mission.yaml --vehicle vehicle.yaml \
  --output my-flight-001_trace.json
```

Supplying `--mission`/`--vehicle` embeds their content hashes, which
`validate` requires. Ingestion snapshots the source bytes before parsing; the
hard size ceiling is 64 MiB (`--max-size-mib` can only lower it).

## convert / export

QGroundControl `.plan` interchange, in both directions:

```bash
# .plan -> mission.v7 YAML (--vehicle-profile is required)
uv run bvlos-sim convert plan.plan --vehicle-profile quadplane_v1 -o mission.yaml

# mission.v7 YAML -> .plan
uv run bvlos-sim export mission.yaml -o mission.plan
```

`convert` reads the planned home, cruise/hover speeds, and supported mission
items (takeoff, VTOL takeoff, waypoint, loiter-time, RTL, land, VTOL land).
Altitude frames map onto `altitude_reference`: frame `0` -> `amsl`, frame `3`
-> `relative_home`, frame `10` (terrain) -> `terrain`; mixed frames become
per-item overrides.

Conversion is **fail-closed**: any dropped item (Survey/ComplexItem, an
unsupported MAVLink command, an unknown altitude frame) and any populated
`geoFence` or `rallyPoints` section is a loss. By default every loss is listed
on stderr (kind plus item index or section), nothing is written, and the
command exits `12`. `--allow-lossy` restores convert-what-we-can behavior:
each loss is still reported on stderr and the run ends with a one-line
summary — `lossy conversion: N item(s) dropped, sections: geoFence,
rallyPoints` — so lossy imports stay visible in CI logs. `--validate-only`
reports the same losses under the same exit-code contract.

`export` maps route actions back to MAVLink commands and omits
bvlos-sim-specific fields (`constraints`, `assets`, `policy`) with a stderr
note. Semantic rewrites — `terrain` altitudes falling back to frame `3`, a
fixed-wing `takeoff` exported as VTOL takeoff — are warned per item and
summarised with the same one-line `lossy conversion` summary, but `export`
keeps exit `0`: the `.plan` format simply cannot represent them. The result
round-trips through `convert`.

## migrate

Upgrade an unversioned or `mission.v6` file to `mission.v7`. Only this command
treats a missing `schema_version` as legacy.

```bash
uv run bvlos-sim migrate mission.yaml --dry-run    # show versions + diff, write nothing
uv run bvlos-sim migrate mission.yaml --backup     # in-place, writes FILE.bak first
uv run bvlos-sim migrate missions/ --glob "*.yaml" --backup
```

Migration refuses semantic guesses: SORA 2.0 blocks, applied legacy
mitigation declarations, and ambiguous classifications require operator
reassessment instead of silent relabeling.

## sitl / compare

Build SITL evidence bundles and compare them against deterministic
expectations. See [SITL](sitl.md) for the container setup, the live workflow,
and the adapter contract.

```bash
# contract-only bundle from an existing scenario
uv run bvlos-sim sitl SCENARIO --output evidence.json

# live run against a running ArduPilot SITL
uv run bvlos-sim sitl SCENARIO --live --host 127.0.0.1 --port 5770 \
  --artifact-dir artifacts/ --output evidence.json

# compare a completed bundle against its embedded expectations
uv run bvlos-sim compare evidence.json --output comparison.json
```

## verify

Re-verify the chain of custody of a `sitl-evidence.v1` bundle: recompute the
SHA-256 of every referenced artifact file (relative paths resolve against the
bundle's directory) and compare against the recorded checksums.

**Usage:** `bvlos-sim verify EVIDENCE.json`

One line per artifact — `OK`, `MISMATCH`, `MISSING`, or `SKIPPED` (no
recorded checksum) — then a final verdict. Exit `0` when everything matches,
`10` on any mismatch or missing artifact, `11` for an unreadable or invalid
bundle.

## Provenance and output safety

Three flags exist for evidence hygiene, all default-off so outputs stay
byte-identical unless you opt in:

- `--operator-id TEXT` (`estimate`, `scenario`, `sitl`) — records the
  operator identity in the result's free-form metadata map.
- `--generated-at ISO8601|now` (same commands) — records a generation
  timestamp; `now` resolves to the current UTC time.
- `--no-clobber` (every command with `--output`) — refuse to overwrite an
  existing output file (exit `11`) instead of replacing it, so a re-run
  cannot silently destroy prior evidence.

## schema-versions

Print every supported input and output contract version plus the tool version
as canonical JSON, without loading any file. Alias: `contracts`. Use it to pin
compatibility from a backend instead of parsing versions off an envelope.

## bump

Developer-only release tool (absent from published wheels): bumps the version
in `pyproject.toml` and rolls `CHANGELOG.md`. `--dry-run` previews, `--check`
fails CI when the version is behind the latest `v*` tag. It never tags,
pushes, or publishes.

## Map exports

`estimate --format geojson|kml` (and the same on `scenario`) emit the computed
route as map layers; `batch --format geojson|kml` with `--output-dir` writes
one file per run.

GeoJSON layers (RFC 7946, coordinates `[lon, lat, altitude_m]`):

- `route` — one LineString per leg with `leg_id`, `action`,
  `energy_margin_pct`, and RTH reserve margin/color when available.
- `landing_zones` — one Point per zone with `zone_id` and `reachable`.
- `geofences` — one Polygon per zone with `kind` and `conflict`.
- `obstacles` — configured obstacle geometries with `height_m` and `conflict`.

Color thresholds (energy and RTH margin as percent of battery capacity):
`green` above 30, `amber` 10–30, `red` below 10. KML uses the same thresholds
and opens directly in Google Earth and QGroundControl; GeoJSON opens in QGIS
and QGroundControl.

## Advisory warnings

Warnings mark conditions that do not make the mission infeasible but block an
operational `GO` (they appear in `failed_checks` as `warnings`). The full JSON
envelope carries each warning's `code`, `message`, and location; the checklist
lists the codes on its `Advisory warnings` row.

A reviewed warning can be accepted per mission via
`constraints.accepted_warning_codes` (see
[Missions and vehicles](missions.md#constraints)): acknowledged codes stay in
every artifact but stop blocking `GO`; any unlisted warning still blocks.

| Code | Meaning |
|------|---------|
| `MAX_WIND_EXCEEDED` | Leg wind exceeds `vehicle.performance.max_wind_mps` (not enforced as a hard limit). |
| `RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD` | Predicted landing reserve is below the autopilot abort threshold. |
| `RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD` | Predicted landing reserve is below the low-battery warning threshold. |
| `GEOFENCE_EVALUATED_2D_ONLY` | Geofence intersection is 2D; declared `floor_m`/`ceiling_m` bounds are checked, per-zone AGL is not modeled. |
| `GEOFENCE_ZERO_ZONES` | A geofence file is configured but contains zero zones — the clearance check evaluated no airspace. |
| `OBSTACLE_ZERO_FEATURES` | An obstacle file is configured but contains zero obstacles — the clearance check evaluated no vertical structure. |
| `OBSTACLE_KEEP_OUT_NOT_CONFIGURED` | Every obstacle has zero radius and uncertainty and `min_obstacle_clearance_m` is unset, so the keep-out volume has no width. |
| `DEPARTURE_TIME_MISSING` | A geofence has a time window but the mission has no `departure_time`; the zone is treated as always active. |
| `DIVERT_ENERGY_TAS_ONLY` | A scenario divert estimate used TAS without wind correction. |
| `POPULATION_DENSITY_DIMENSION_MISSING` | Population grid present but the vehicle omits `characteristic_dimension_m`; iGRC cannot be computed. |
| `GUST_DATA_UNAVAILABLE` | `max_gust_mps` is set but no provider supplies gust data. |
| `ENERGY_REFERENCE_CONDITIONS_MISSING` | The vehicle declares `operating_mass_kg` without `reference_mass_kg` (or a reference density), so mass/density scaling is inert. |
| `ROUTE_ACTIONS_AFTER_RTL` | Route items after an RTL are estimated but unreachable. |
| `LOITER_RADIUS_IGNORED` | `loiter_radius_m` is ignored; loiter is modeled as station-keep. |
| `LOITER_ASSUMED_ZERO_GROUND_DISTANCE` | Loiter dwell is modeled with zero ground-path distance. |
| `LOW_GROUNDSPEED_MARGIN` | Groundspeed within 10% of `min_groundspeed_mps`. |
| `HIGH_CRAB_MARGIN` | Crab angle within 10% of `max_crab_angle_deg`. |
| `HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY` | `max_station_keep_wind_mps` unset; `hover_speed_mps` used as fallback. |

## Python API

The stable Python surface is `bvlos_sim.estimator`:

```python
from bvlos_sim.estimator import (
    EstimationOptions, FidelityMode, LayeredWindProvider, WindLayer,
    estimate_mission_distance_time, try_estimate_mission_distance_time,
    run_scenario, run_monte_carlo,
)

result = estimate_mission_distance_time(
    mission, vehicle,
    wind_provider=LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
        WindLayer(altitude_m=500.0, wind_east_mps=6.0, wind_north_mps=-1.0),
    ]),
    options=EstimationOptions(fidelity=FidelityMode.V2, max_segment_length_m=500.0),
)
```

Symbols exported from `bvlos_sim.estimator.__all__` are the supported surface; internal
module layout is not a contract.
