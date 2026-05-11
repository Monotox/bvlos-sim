# BVLOS Simulator

Deterministic BVLOS mission validation and simulation tooling for Python and the
command line.

License: [MIT](./LICENSE)

bvlos-sim estimates route distance, time, energy feasibility, static geofence
conflicts, landing-zone reachability and deterministic scenario assertions from
versioned YAML or JSON inputs.

## Disclaimer

bvlos-sim is not a flight-safety system, operational approval tool or complete
BVLOS compliance system. Do not use it as the sole basis for operational BVLOS
decisions.

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

Run with fidelity v2:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2
```

Run the example scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Run the checks:

```bash
uv run ruff check .
uv run pytest
```

Full usage details are in [docs/USAGE.md](./docs/USAGE.md).

## Status

The current codebase includes:

- deterministic mission distance/time estimation
- estimator CLI command surface (`estimate`)
- scenario CLI command surface (`scenario`)
- canonical JSON envelopes and optional Markdown reports
- deterministic energy feasibility and reserve-at-landing output
- resource-system feasibility for onboard battery, external power, and hybrid power configurations
- communication-link feasibility for mission and scenario link systems
- static GeoJSON geofence feasibility checks
- static GeoJSON landing-zone reachability checks
- deterministic scenario runner with event injection, wind-change events, and assertions (`scenario.v1`)
- comms-link lost-link policy model with `rtl`, `land`, `loiter`, and `divert` actions
- layered wind, optional sub-segment sampling, turn-arc dynamics, and fixed-wing circular loiter
- terrain-referenced altitude using an offline uniform elevation grid
- spatiotemporal wind grid with quadrilinear interpolation (offline 4D wind data)
- documented schema/versioning policy with golden contract fixtures
- passing test suite

The next roadmap areas are bank-angle path optimization and SITL integration.
See [docs/ROADMAP.md](./docs/ROADMAP.md) for the full roadmap and known
limitations.

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

- [Contribution style](./docs/CODE_STYLE.md)
  Technical rules for package boundaries, output contracts, validation, testing, and docs.

- [Ticket backlog](./docs/tickets/README.md)
  Ordered execution backlog from estimator hardening through later platform phases.

## Code Layout

- `adapters/`
  CLI, file loading, result envelope building, and Markdown rendering adapters.

- `schemas/`
  Mission, vehicle, and scenario input models.

- `estimator/`
  Deterministic estimator package:
  - `core/` for public enums/options/results, constants, and typed errors
  - `execution/` for orchestration, executors, runtime models, context-building, rules, altitude, vertical, transit, loiter, and scenario logic
  - `environment/` for wind and terrain providers
  - `math/` for wind-triangle and turn-arc helpers

- `examples/`
  Example mission, vehicle, and scenario files.

- `tests/`
  Schema, estimator, scenario, envelope, and CLI coverage.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, test commands,
pull request expectations, commit message conventions, and public contract rules.
