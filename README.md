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

✓ Energy feasibility        PASS   reserve 603.56 Wh above threshold (828.56 Wh at landing, 225.00 Wh threshold)
◌ Geofence clearance        N/A    not evaluated
✓ Landing-zone coverage     PASS   reachable zone found at all 166 checked state(s)
◌ Resource availability     N/A    not evaluated
✓ Weather limits            PASS   worst wind 3.55 m/s at leg 3 (rtl)
✓ RTH reserve               PASS   reserve intact for RTH from all 4 leg(s)
  Warnings                  1      ENERGY_MODEL_UNCALIBRATED

Status: NO-GO
Blocked by: missing evidence (geofence, resource, link, obstacle, ground_risk); blocking warnings (ENERGY_MODEL_UNCALIBRATED) — the checklist is fail-closed

$ bvlos-sim estimate alpine_infeasible.yaml small_battery.yaml --format summary
INFEASIBLE   reserve −36.2 %   flight 7m 58s   RTH infeasible   warnings 1   [RESERVE_BELOW_THRESHOLD]
```

A `GO` is reachable, and the repository ships the mission that earns one — every
evidence category supplied, coefficients calibrated from a flight log, no
warning waived:

```text
$ bvlos-sim estimate examples/missions/pipeline_demo_001_go.yaml \
    examples/vehicles/quadplane_v1_complete.yaml \
    --calibration examples/calibration/quadplane_v1_calibration.json \
    --format checklist
...
✓ Obstacle clearance        PASS   0 violations across 3 leg(s) and 1 obstacle(s)
✓ Weather limits            PASS   worst wind 2.72 m/s at leg 1 (wp1)
✓ RTH feasibility           PASS   selected external resource covers RTH peak power
  Ground risk class         INFO   mission iGRC 3
  Warnings                  NONE

Status: GO
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
The [getting-started tutorial](./docs/getting-started.md) walks through both,
then through the complete-evidence mission that earns a `GO`.

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

[MIT](./LICENSE) — for this project's own code, docs, and synthetic data.

Some bundled example assets are derived from third-party databases with their
own terms that MIT cannot override: OpenStreetMap landing zones and airspace
(ODbL 1.0) and Open-Meteo wind (CC BY 4.0). If you redistribute them, or data
you fetch yourself with the `bvlos-fetch-*` commands, the attribution and
share-alike obligations in [NOTICE](./NOTICE.md) travel with you.
