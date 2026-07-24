# BVLOS Simulator

> Preflight energy, geofence, and contingency checker for beyond-visual-line-of-sight (BVLOS) drone operations

[![CI](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml/badge.svg)](https://github.com/Monotox/bvlos-sim/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Docs](https://img.shields.io/badge/docs-github.io-blue.svg)](https://monotox.github.io/bvlos-sim/)

Two YAML files — a mission and a vehicle profile — answer the questions no
spreadsheet handles: does this aircraft keep its reserve given tomorrow's wind
over this terrain, does the route clip restricted airspace, and can it still
fly home from every waypoint? The answer is deterministic, reproducible, and
fail-closed: missing evidence can never produce a `GO`.

```text
$ bvlos-sim estimate alpine_mission.yaml quadplane_v1.yaml --format checklist

## Pre-Flight Checklist: alpine_demo_001

✓ Energy feasibility        PASS   reserve 573.05 Wh above threshold (798.05 Wh at landing, 225.00 Wh threshold)
◌ Geofence clearance        N/A    not evaluated
✓ Landing-zone coverage     PASS   reachable zone found at all 166 checked state(s)
◌ Resource availability     N/A    not evaluated
✓ Weather limits            PASS   worst wind 0.00 m/s at leg 0 (takeoff)
✓ RTH reserve               PASS   reserve intact for RTH from all 4 leg(s)

Status: NO-GO
Blocked by: missing evidence (geofence, resource, link, obstacle, ground_risk) — the checklist is fail-closed

$ bvlos-sim estimate alpine_infeasible.yaml small_battery.yaml --format summary
INFEASIBLE   reserve −179.7 %   flight 7m 55s   RTH infeasible   [INSUFFICIENT_ENERGY]
```

## Quickstart

```bash
git clone https://github.com/Monotox/bvlos-sim && cd bvlos-sim
uv sync

# pre-fetched Alpine demo: real SRTM terrain, Open-Meteo wind, OSM landing zones — no network
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --format checklist
```

Expect `Status: NO-GO` and exit `10` — the demo deliberately omits
geofence/resource/link/obstacle/ground-risk evidence, and the checklist is
fail-closed.
Add `--engineering-only` for the pure-physics verdict (`FEASIBLE`, exit `0`).
The [getting-started tutorial](./docs/getting-started.md) walks through both.

## Usage

Fetch real terrain, wind, and landing zones for your own area:

```bash
uv sync --extra scripts
uv run python bvlos_sim/scripts/fetch_all.py <lat> <lon> --output-dir assets/
# prints the assets: block to paste into your mission YAML
```

Ask what battery the mission actually needs:

```bash
uv run bvlos-sim size-battery mission.yaml vehicle.yaml --margin 20
```

Test contingencies — inject a lost link at a waypoint and assert the divert
still lands with reserve:

```bash
uv run bvlos-sim scenario examples/scenarios/pipeline_demo_001_scenario.yaml
```

Check the model against a real flight, then calibrate it:

```bash
uv run bvlos-sim ingest-log flight.bin --trace-id f1 -o trace.json \
  --mission mission.yaml --vehicle vehicle.yaml
uv run bvlos-sim validate mission.yaml vehicle.yaml trace.json
uv run bvlos-sim calibrate vehicle.yaml trace.json --format json -o cal.json
uv run bvlos-sim estimate mission.yaml vehicle.yaml --calibration cal.json
```

Seventeen commands cover estimation, batch runs, Monte Carlo diagnostics,
SORA 2.5 pre-assessment, QGroundControl import/export, and ArduPilot SITL
evidence — the [CLI reference](./docs/cli.md) documents every one, with exit
codes. Outputs are versioned JSON envelopes plus Markdown, one-line summary,
checklist, GeoJSON, and KML renderings that open in QGroundControl, QGIS, and
Google Earth.

## What it checks

- **Energy** — per-phase power with a wind triangle solved per leg, so an
  outbound headwind isn't averaged away by the tailwind home; reserve at
  landing plus a return-to-home reserve gate at every leg.
- **Environment** — per-leg SRTM terrain, spatiotemporal wind grids,
  geometric geofence intersection with altitude bounds and time windows,
  landing-zone reachability with Dubins divert paths, obstacle clearance.
- **Contingency** — scenario events (lost link, wind change, landing zone
  loss) with RTL/land/loiter/divert policy outcomes and CI-ready assertions.
- **Risk** — SORA 2.5 iGRC/ARC/SAIL pre-assessment, strictly evidence-gated.
- **Uncertainty** — seeded Monte Carlo and stochastic-propagation
  diagnostics with conditional p5/p50/p95 envelopes.

## Scope

bvlos-sim is a deterministic, offline feasibility model — an early,
auditable gate *before* regulator-facing tooling and flight testing. It has
no regulatory standing, uses no live data, ships placeholder vehicle profiles
you must calibrate against your own logs, and is MIT-licensed with no
warranty. A `GO` is only as current as your inputs. The reasoning is in
[Design](./docs/design.md).

## Documentation

- [Getting started](./docs/getting-started.md) — zero to first verdict in five minutes.
- [CLI reference](./docs/cli.md) — every command, format, and exit code.
- [Missions and vehicles](./docs/missions.md) — authoring all input YAML, field by field.
- [SITL](./docs/sitl.md) — the ArduPilot container and evidence workflow.
- [Design](./docs/design.md) — fail-closed philosophy, scope, architecture, contracts.
- [Roadmap](./docs/roadmap.md) — status and known gaps; [ticket backlog](./docs/tickets/README.md) for the work log.
- [Contributing](./CONTRIBUTING.md) — setup, tests, style, and contract rules.

## License

[MIT](./LICENSE)
