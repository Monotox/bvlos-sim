# BVLOS Simulator

> Preflight energy, geofence, and contingency checker for beyond-visual-line-of-sight (BVLOS) drone operations

[![CI](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml/badge.svg)](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Docs](https://img.shields.io/badge/docs-github.io-blue.svg)](https://monotox.github.io/bvlos-sim/)

📖 **Documentation site: [monotox.github.io/bvlos-sim](https://monotox.github.io/bvlos-sim/)**

Two YAML files — a mission and a vehicle profile — answer the questions no spreadsheet handles: does this aircraft have enough reserve given tomorrow's wind over this terrain, does the route cross any restricted airspace, and what is the p5 reserve margin if wind is 2 m/s stronger than forecast?

```
$ bvlos-sim estimate alpine_mission.yaml quadplane_v1.yaml --format checklist

## Pre-Flight Checklist: alpine_demo_001

✓ Energy feasibility        PASS   reserve 605.78 Wh above threshold (830.78 Wh at landing, 225.00 Wh threshold)
✓ Geofence clearance        PASS   0 conflicts across 0 zone(s)
✓ Landing-zone coverage     PASS   reachable zone found at all 4 checked state(s)
◌ Resource availability     N/A    not evaluated
◌ Link availability         N/A    not evaluated
  Advisory warnings         1      DIVERT_ENERGY_TAS_ONLY

Status: GO

$ bvlos-sim estimate alpine_infeasible.yaml small_battery.yaml --format summary
INFEASIBLE   reserve −25.7 %   flight 7m 55s   [RESERVE_BELOW_THRESHOLD]

$ bvlos-sim sample wind_uncertainty.yaml --format summary
feasible 100%   reserve p5 823.9 Wh   p50 858.2 Wh   p95 903.3 Wh   time p50 2m 50s   n=200
```

JSON envelopes, one-line go/no-go summaries, and GeoJSON/KML exports that open in QGroundControl, QGIS, and Google Earth.

## Quick Start

```bash
# install
uv sync

# run the pre-fetched Alpine demo (SRTM terrain, Open-Meteo wind, Overpass LZs — no network)
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --format checklist

# see it fail with a smaller battery
uv run bvlos-sim estimate \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery.yaml \
  --format summary
```

Five ready-to-use vehicle profiles are in
[`examples/vehicles/community/`](./examples/vehicles/community/) (DJI Matrice 300 RTK,
Wingtra One Gen II, Trinity F90+, Autel EVO Max 4T, generic survey hexacopter).
When swapping vehicles, set `mission.vehicle_profile` to the profile's `vehicle_id`.

Fetch live terrain, wind, and landing zones for any area:

```bash
uv sync --extra scripts   # installs srtm.py (once)
uv run python scripts/fetch_all.py <lat> <lon> --departure-time HH:MM --output-dir assets/
```

This writes `terrain.yaml`, `wind_grid.yaml`, and `landing_zones.geojson` and
prints the `assets:` block to paste into your mission YAML. See
[`examples/real_world/README.md`](./examples/real_world/README.md) for details.

<details>
<summary>More commands</summary>

Run with fidelity v2 (turn arcs, sub-segment wind sampling):

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2
```

Run a scenario (lost-link injection and policy assertions):

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Convert a QGroundControl plan:

```bash
uv run bvlos-sim convert examples/missions/pipeline_demo_001.plan \
  --output /tmp/pipeline_converted.yaml
```

Run a batch of estimates:

```bash
uv run bvlos-sim batch examples/batch/demo_batch.yaml
```

Run Monte Carlo uncertainty sampling:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format summary
```

Run time-stepped stochastic propagation (per-step reserve-violation probability):

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format summary
```

For SITL evidence recording and comparison against ArduPilot, see
[SITL adapter contract](./docs/SITL_ADAPTER_CONTRACT.md).

</details>

Run the checks:

```bash
uv run ruff check .
uv run pytest
```

Full usage details are in [docs/USAGE.md](./docs/USAGE.md).

## Commands

- `estimate`: deterministic mission estimation and static feasibility checks
- `scenario`: deterministic scenario events and assertions
- `convert`: convert a QGroundControl `.plan` file to a `mission.v6` YAML
- `batch`: batch mission estimates from a manifest file
- `sample`: seeded Monte Carlo uncertainty sampling
- `propagate`: time-stepped stochastic state propagation with EKF and tracking controller
- `sitl`: build a contract-only or live SITL evidence bundle
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations
- `sora`: SORA Ground Risk, Air Risk, and SAIL pre-assessment
- `validate`: compare a predicted mission estimate against an observed flight trace

`compare` exits `0` for a passing comparison and `10` for drifted, failed, or
unsupported comparison summaries.

## What You Can Do

### Pre-flight feasibility

- **Energy model** — separate power figures for hover, climb, cruise, and loiter; wind-triangle correction per leg so headwind on the outbound leg and tailwind on return are not averaged away.
- **Terrain** — per-leg elevation from an offline SRTM grid; a route over rising ground is estimated correctly, not assumed flat.
- **Geofence** — spatial intersection against real GeoJSON polygons for every route leg, with optional AMSL `floor_m`/`ceiling_m` altitude bounds for forbidden and required zones.
- **Landing zones** — confirms at least one suitable landing point is within transit range.
- **Resource and link** — models battery, tethered, and hybrid power; direct, cellular, satellite, and hybrid failover link architectures.
- **Ground risk** — computes SORA-style iGRC pre-assessment from an offline population-density grid and vehicle characteristic dimension.
- **SORA pre-assessment** — derives Air Risk Class and SAIL, then applies declared mitigations (M1/M2/M3 ground-risk credits and tactical air-risk reduction) to report the final GRC, residual ARC, and mitigated SAIL with the applicable OSOs.

### Environmental data

Fetch scripts pull real data into bvlos-sim's YAML asset format:

- `fetch_wind.py` — Open-Meteo forecast at 10 m, 80 m, 120 m, 180 m, aligned to your departure time.
- `fetch_terrain.py` — SRTM tiles for any bounding box.
- `fetch_landing_zones.py` — Overpass API helipads and aerodromes.
- `fetch_geofences.py` — OpenAIP static airspace polygons with Overpass fallback.
- `fetch_population.py` — WorldPop population-density samples for SORA iGRC pre-assessment.
- `fetch_all.py` — terrain, wind, and landing zones in a single command.

A pre-fetched Alpine example (Lucerne/Zug area) runs offline with no network calls.

### Uncertainty and risk

- **`sample`** — seeded Monte Carlo draws over wind, cruise speed, cruise power, and battery capacity; reports p5/p50/p95 reserve-at-landing against the deterministic baseline.
- **`propagate`** — time-stepped particle propagator emitting per-step `p_reserve_violation` so you see where mid-flight energy risk peaks, not only the landing value. A twin-state EKF carries true physics state and the autopilot's estimated state separately; a cross-track controller converts estimation error into actual deviation and secondary energy burn.

### Contingency planning

`bvlos-sim scenario` injects a lost-link event at a named waypoint, a wind-change at elapsed time, or a landing zone becoming unavailable. The lost-link policy model evaluates RTL, land, loiter, and divert, and emits a Dubins-path divert estimate (bank-angle-constrained arc + straight segment, transit time, reserve remaining). Assertions are machine-readable and suitable for CI gates.

### Validation against real flights

`bvlos-sim validate MISSION.yaml VEHICLE.yaml TRACE.json` compares a predicted
mission estimate against an observed flight. A real ArduPilot DataFlash log is
ingested into a normalized trace, segmented into flight phases, and lined up
against the estimator's legs on shared phase keys. The report gives
predicted-vs-observed time, horizontal distance, mean groundspeed, and reserve
at landing — at both mission and per-phase level, each with absolute and percent
error. This is how you measure where the model is accurate and where it drifts on
your own aircraft. Calibrating the model from those residuals is the next step on
the [calibration & validation track](./docs/tickets/README.md#calibration--validation-track).

### Output formats

All commands emit versioned JSON envelopes (`estimator-envelope.v7`,
`scenario-report.v2`, `uncertainty-report.v1`, `stochastic-envelope.v1`,
`validation-report.v1`) and optional Markdown reports.

`estimate`, `scenario`, `sample`, and `propagate` support `--format summary` for a
single-line terminal check:

```
FEASIBLE   reserve 281.6 %   flight 2m 49s
feasible 100%   reserve p5 823.9 Wh   p50 858.2 Wh   p95 903.3 Wh   time p50 2m 50s   n=200
```

`estimate --format geojson` and `--format kml` (and the same on `scenario`) emit the
route as map-ready layers: one LineString per leg, landing-zone points with reachability
markers, and geofence polygons with conflict flags. GeoJSON opens in QGroundControl and
QGIS; KML opens in Google Earth.

`estimate --format checklist` (and the same on `scenario`) renders a pre-flight go/no-go
checklist with `✓`, `✗`, and `◌` icons per category (energy, geofence, landing zone,
resource, link, warnings) and a final `Status: GO/NO-GO` line suitable for briefing notes
or CI gates.

`estimate --format profile` (and the same on `scenario`) renders a per-leg altitude table
with terrain elevation and clearance columns when a terrain provider is configured.

`estimate --format ground-risk` renders the mission and per-leg iGRC values when
the mission references a population grid and the vehicle supplies
`characteristic_dimension_m`.

### Why not a spreadsheet

A spreadsheet applies one wind speed to a flat total distance and checks whether a single
energy number stays positive. bvlos-sim applies a wind-triangle correction to every transit
leg using a spatiotemporal forecast grid, resolves terrain elevation per leg from SRTM, and
performs geometric intersection between your route and actual GeoJSON airspace polygons.
The result: `reserve_at_landing_wh` with a p5/p95 envelope from seeded Monte Carlo draws, a
per-assertion scenario report showing whether your RTL policy leaves the aircraft with
positive reserve after a Dubins-constrained divert, and a per-step reserve-violation
probability from the particle propagator. Two YAML files, no Python.

## Scope & limitations

bvlos-sim is a deterministic, offline **feasibility model** — a transparent
pre-flight sanity check, not a flight-safety system, operational approval tool,
or complete BVLOS compliance system. Do not use it as the sole basis for
operational BVLOS decisions. Be aware of what it deliberately does **not**
provide:

- **No regulatory standing.** Its outputs (including the SORA pre-assessment) are
  not recognised or accepted by any aviation authority and do not constitute an
  authorization, a LAANC clearance, or a certified SORA determination.
- **No live or guaranteed-current data.** Airspace, weather, terrain, and
  population come from static files you fetch and commit yourself; there is no
  real-time feed and no currency guarantee. A "GO" is only as current as your
  inputs.
- **A model with sample data, calibrated by you.** The shipped vehicle profiles
  are placeholders. The estimator can now be checked against real flights —
  `bvlos-sim validate` reports predicted-vs-observed error per mission and per
  phase from an ingested flight log — but the shipped profiles have not themselves
  been fitted to measured data. Replace profiles with your own, validate against
  your logs, and treat results as indicative until you have done so.
- **No warranty, support, or liability transfer.** MIT-licensed and provided
  "as is" (see [LICENSE](./LICENSE)).

Where it is genuinely useful: an early, reproducible, auditable feasibility gate
*before* you engage regulator-facing tooling and real flight testing. See the
[ticket backlog](./docs/tickets/README.md) for planned accuracy and integration
work, and the [roadmap](./docs/ROADMAP.md) for known limitations.

## Documentation

- [Usage](./docs/USAGE.md)
  CLI commands, output formats, exit codes, YAML configuration, and verification commands.

- [Project brief](./docs/BVLOS_MISSION_SIMULATOR_BRIEF.md)
  Product framing and architecture direction.

- [Roadmap](./docs/ROADMAP.md)
  Current implementation status, limitations, phase plan, and validation track.

- [Estimator field semantics](./docs/ESTIMATOR_V1_FIELD_SEMANTICS.md)
  Operative and non-operative schema fields for current estimator behavior.

- [Versioning policy](./docs/VERSIONING_POLICY.md)
  Public contract surfaces, compatibility rules, and golden fixture expectations.

- [SITL adapter contract](./docs/SITL_ADAPTER_CONTRACT.md)
  Evidence schema, CLI shape, and live-adapter dependency boundaries.

- [Contribution style](./docs/CODE_STYLE.md)
  Technical rules for package boundaries, output contracts, validation, testing, and docs.

- [Ticket backlog](./docs/tickets/README.md)
  Ordered execution backlog from estimator hardening through later platform phases.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, test commands,
pull request expectations, commit message conventions, and public contract rules.
