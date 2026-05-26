# BVLOS Simulator

[![CI](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml/badge.svg)](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml)

Answer the three questions no flight-planning app handles: does this aircraft have enough
reserve given tomorrow's wind over this terrain, does the route cross any restricted
airspace that went live this week, and what is the p5 reserve margin if wind is 2 m/s
stronger than forecast?

Two YAML files and one command. JSON envelopes, one-line go/no-go summaries, and
GeoJSON exports that open in QGroundControl, QGIS, and Google Earth.

License: [MIT](./LICENSE)

## Quick Start

Install dependencies:

```bash
uv sync
```

Run the example mission:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml
```

Run with fidelity v2 (turn arcs, terrain-referenced altitude):

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2
```

Five ready-to-use vehicle profiles are in
[`examples/vehicles/community/`](./examples/vehicles/community/) (DJI Matrice 300 RTK,
Wingtra One Gen II, Trinity F90+, Autel EVO Max 4T, generic survey hexacopter).
When swapping vehicles, set `mission.vehicle_profile` to the profile's `vehicle_id`.

Run the real-world Alpine demo (pre-fetched SRTM terrain, Open-Meteo wind,
and Overpass landing zones — no network required):

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml
```

Run the infeasible variant to see a failing reserve check:

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery.yaml \
  --format summary
```

Fetch terrain, wind, and landing zones for any area in one command:

```bash
uv sync --extra scripts   # installs srtm.py (once)
uv run python scripts/fetch_all.py <lat> <lon> --departure-time HH:MM --output-dir assets/
```

This writes `terrain.yaml`, `wind_grid.yaml`, and `landing_zones.geojson` and
prints the `assets:` block to paste into your mission YAML. See
[`examples/real_world/README.md`](./examples/real_world/README.md) for details.

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

For SITL evidence recording and comparison against ArduPilot, see
[SITL adapter contract](./docs/SITL_ADAPTER_CONTRACT.md).

Run the checks:

```bash
uv run ruff check .
uv run pytest
```

Full usage details are in [docs/USAGE.md](./docs/USAGE.md).

## Commands

- `estimate`: deterministic mission estimation and static feasibility checks
- `scenario`: deterministic scenario events and assertions
- `convert`: convert a QGroundControl `.plan` file to a `mission.v5` YAML
- `batch`: batch mission estimates from a manifest file
- `sample`: seeded Monte Carlo uncertainty sampling
- `propagate`: time-stepped stochastic state propagation with EKF and tracking controller
- `sitl`: build a contract-only or live SITL evidence bundle
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations

`compare` exits `0` for a passing comparison and `10` for drifted, failed, or
unsupported comparison summaries.

## What You Can Do

### Pre-flight feasibility

- **Energy model** — separate power figures for hover, climb, cruise, and loiter; wind-triangle correction per leg so headwind on the outbound leg and tailwind on return are not averaged away.
- **Terrain** — per-leg elevation from an offline SRTM grid; a route over rising ground is estimated correctly, not assumed flat.
- **Geofence** — spatial intersection against real GeoJSON polygons (forbidden and caution zones) for every route leg.
- **Landing zones** — confirms at least one suitable landing point is within transit range.
- **Resource and link** — models battery, tethered, and hybrid power; direct, cellular, satellite, and hybrid failover link architectures.

### Environmental data

Four fetch scripts pull real data into bvlos-sim's YAML asset format:

- `fetch_wind.py` — Open-Meteo forecast at 10 m, 80 m, 120 m, 180 m, aligned to your departure time.
- `fetch_terrain.py` — SRTM tiles for any bounding box.
- `fetch_landing_zones.py` — Overpass API helipads and aerodromes.
- `fetch_geofences.py` — OpenAIP static airspace polygons with Overpass fallback.
- `fetch_all.py` — terrain, wind, and landing zones in a single command.

A pre-fetched Alpine example (Lucerne/Zug area) runs offline with no network calls.

### Uncertainty and risk

- **`sample`** — seeded Monte Carlo draws over wind, cruise speed, cruise power, and battery capacity; reports p5/p50/p95 reserve-at-landing against the deterministic baseline.
- **`propagate`** — time-stepped particle propagator emitting per-step `p_reserve_violation` so you see where mid-flight energy risk peaks, not only the landing value. A twin-state EKF carries true physics state and the autopilot's estimated state separately; a cross-track controller converts estimation error into actual deviation and secondary energy burn.

### Contingency planning

`bvlos-sim scenario` injects a lost-link event at a named waypoint, a wind-change at elapsed time, or a landing zone becoming unavailable. The lost-link policy model evaluates RTL, land, loiter, and divert, and emits a Dubins-path divert estimate (bank-angle-constrained arc + straight segment, transit time, reserve remaining). Assertions are machine-readable and suitable for CI gates.

### Output formats

All commands emit versioned JSON envelopes (`estimator-envelope.v5`,
`scenario-report.v2`, `uncertainty-report.v1`, `stochastic-envelope.v1`) and
optional Markdown reports.

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

### Why not a spreadsheet

A spreadsheet applies one wind speed to a flat total distance and checks whether a single
energy number stays positive. bvlos-sim applies a wind-triangle correction to every transit
leg using a spatiotemporal forecast grid, resolves terrain elevation per leg from SRTM, and
performs geometric intersection between your route and actual GeoJSON airspace polygons.
The result: `reserve_at_landing_wh` with a p5/p95 envelope from seeded Monte Carlo draws, a
per-assertion scenario report showing whether your RTL policy leaves the aircraft with
positive reserve after a Dubins-constrained divert, and a per-step reserve-violation
probability from the particle propagator. Two YAML files, no Python.

## Disclaimer

bvlos-sim is not a flight-safety system, operational approval tool, or complete
BVLOS compliance system. Do not use it as the sole basis for operational BVLOS
decisions.

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
