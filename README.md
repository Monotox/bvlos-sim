# BVLOS Simulator

The day before a BVLOS flight, you have three questions a flight planning app
won't answer: does this aircraft have enough reserve given tomorrow's actual
forecast wind over this terrain, does the route cross any restricted airspace
that went live this week, and what happens to energy if the wind is 2 m/s
stronger than forecast? bvlos-sim answers all three from the command line,
producing a per-leg energy and feasibility breakdown, a geofence intersection
check against real GeoJSON airspace polygons, and a Monte Carlo distribution
over reserve margin — in a single estimate run from two YAML files. The outputs
are versioned JSON envelopes, one-line go/no-go summaries suitable for shell
scripts, and GeoJSON exports that open directly in QGroundControl or Google
Earth.

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

Community starter vehicle profiles are available in
[`examples/vehicles/community/`](./examples/vehicles/community/), including
DJI Matrice 300 RTK, Wingtra One Gen II, Trinity F90+, Autel EVO Max 4T, and a
generic survey hexacopter. When swapping vehicles, set
`mission.vehicle_profile` to the selected profile's `vehicle_id`.

Run the real-world Alpine demo (pre-fetched SRTM terrain, Open-Meteo wind,
and Overpass landing zones committed — no network required):

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml
```

Run the infeasible variant to see what a failing reserve check looks like:

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery.yaml \
  --format summary
```

To fetch assets for your own area, run one command:

```bash
uv sync --extra scripts   # installs srtm.py (once)
uv run python scripts/fetch_all.py <lat> <lon> --departure-time HH:MM --output-dir assets/
```

This writes `terrain.yaml`, `wind_grid.yaml`, and `landing_zones.geojson` and
prints the `assets:` block to paste into your mission YAML. See
[`examples/real_world/README.md`](./examples/real_world/README.md) for details.

Run the example scenario (lost-link event injection and policy assertions):

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Run Monte Carlo uncertainty sampling:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_uncertainty.yaml
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

- `estimate`: run deterministic mission estimation and static feasibility checks
- `scenario`: run deterministic scenario events and assertions
- `sample`: run seeded Monte Carlo uncertainty sampling
- `sitl`: build a contract-only or live SITL evidence bundle
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations

`compare` exits `0` for a passing comparison and `10` for drifted, failed, or
unsupported comparison summaries.

## What You Can Do

### Pre-flight feasibility (available now)

bvlos-sim runs a deterministic phase-based energy model — separate power
figures for hover, climb, cruise, and loiter — and reports reserve at landing
against a configurable threshold. Each transit leg applies a wind-triangle
correction using your wind model, so headwind on the outbound leg and tailwind
on return are not averaged away. Terrain-referenced altitude resolves per-leg
elevation from an offline SRTM grid, so a route over rising ground is estimated
correctly rather than assumed flat. Static geofence feasibility loads actual
GeoJSON polygons — forbidden and caution zones — and performs spatial
intersection checks against every route leg. Landing-zone reachability confirms
that at least one suitable landing point is within transit range. Resource and
communication-link feasibility models battery, tethered, and hybrid power, and
direct, cellular, satellite, or hybrid failover link architectures.

Five ready-to-use vehicle profiles are in `examples/vehicles/community/`: DJI
Matrice 300 RTK, Wingtra One Gen II, Quantum-Systems Trinity F90+, Autel EVO
Max 4T, and a generic survey hexacopter. Each has values sourced from published
spec sheets with derivation notes, so you can start estimating without filling
in placeholder values.

### Environmental realism (available now)

Four fetch scripts eliminate the need for synthetic demo data.
`fetch_wind.py` pulls an Open-Meteo forecast at four altitude bands
(10 m, 80 m, 120 m, 180 m) for a departure time and date, aligning `time_s=0`
to your planned takeoff so wind interpolation is temporally correct.
`fetch_terrain.py` downloads SRTM tiles for any bounding box.
`fetch_landing_zones.py` queries the Overpass API for helipads and aerodromes.
`fetch_geofences.py` fetches static airspace geofences from OpenAIP, with a
keyless Overpass fallback for way-based aeronautical boundaries.
`fetch_all.py` wraps terrain, wind, and landing-zone fetching in a single
command; fetch geofences separately when you need airspace polygons. All
implemented scripts produce files that wire directly into the `assets:`
section of your mission YAML. A
pre-fetched Alpine example covering the Lucerne/Zug area is committed to
`examples/real_world/` and runs offline with no network calls.

One additional fetch script is planned: `fetch_notams.py` for active TFRs and
temporary restrictions from FAA B4UFly or EUROCONTROL (Ticket 058).

### Uncertainty and risk

Monte Carlo uncertainty sampling (`sample` command, available now) runs a
seeded draw over configurable distributions for wind speed, cruise speed, cruise
power, and battery capacity, reporting p5/p50/p95 reserve-at-landing and
total-time distributions against the deterministic baseline.

The planned `propagate` command (Ticket 047, Phase 7) adds a time-stepped
stochastic propagator that carries a belief state forward through the full
trajectory and emits a `p_reserve_violation` value at each time step — not
only at landing. Ticket 048 extends this with a twin-state EKF: true physics
state and the autopilot's estimated state propagate separately, with synthetic
GPS, battery-meter, and airspeed sensor models driving the update step, so
policy triggers fire from the estimated state as they do on a real autopilot.
Ticket 049 adds a closed-loop tracking controller that converts EKF estimation
error into actual cross-track deviation and secondary energy burn.

### Contingency planning (available now)

`bvlos-sim scenario` runs a deterministic event timeline: inject a lost-link
event at a named waypoint, a wind-change at elapsed time, or mark a landing
zone unavailable. The lost-link policy model evaluates RTL, land, loiter, and
divert actions and emits a computed divert route estimate for divert outcomes —
Dubins-path distance (bank-angle-constrained arc + straight segment),
transit time at cruise power, and reserve remaining after divert. Scenario
assertions are machine-readable (`passed`, `failed`, `skipped`, `unsupported`)
and suitable for CI gates.

### Evidence and output

All commands emit versioned JSON envelopes (`estimator-envelope.v5`,
`scenario-report.v2`, `uncertainty-report.v1`) and optional Markdown reports.
The `estimate` and `scenario` commands also support `--format summary` for a
single-line operational summary:

```
FEASIBLE   reserve 281.6 %   flight 2m 49s
PASSED 3/3   reserve 281.6 %   flight 2m 49s   policy NONE
```

The estimate summary reports feasibility, reserve margin, flight time, and the
primary failure code when present. The scenario summary reports assertion
counts, reserve margin, flight time, contingency policy action, and the first
failing assertion when present. These single-line outputs are suitable for
shell pipelines and pre-flight checklists.

`estimate --format geojson`, `estimate --format kml`, and the same formats on
`scenario` emit the route as map-ready layers: one LineString per leg,
landing-zone points with reachability markers, and geofence polygons with
conflict flags. GeoJSON opens directly in QGroundControl and QGIS; KML opens
directly in Google Earth.

### Why not a spreadsheet

A spreadsheet applies one wind speed to a flat total distance and checks
whether a single energy number stays positive. bvlos-sim applies a
wind-triangle correction to every transit leg using a spatiotemporal forecast
grid at four altitude bands, resolves terrain elevation per leg from SRTM so a
route over Alpine foothills does not look like Dutch polder, and performs
geometric intersection between your route and the actual GeoJSON polygons for
the Swiss TMA or the FAA TFR issued 48 hours before departure. A spreadsheet
gives you a scalar go/no-go; bvlos-sim gives you a `reserve_at_landing_wh`
with a p5/p95 envelope from 500 seeded Monte Carlo draws and a per-assertion
scenario report showing whether your RTL policy leaves the aircraft with
positive reserve after a Dubins-constrained divert path. None of that requires
writing Python; it requires two YAML files and three CLI commands.

On the roadmap: once Ticket 047 ships, the planned `propagate` command will add
a per-step `p_reserve_violation` timeline showing where mid-flight energy risk
peaks, not only whether you land inside the threshold.

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
