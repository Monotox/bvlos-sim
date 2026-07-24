# Design

Why bvlos-sim is shaped the way it is: what it models, what it refuses to
model, and the contracts that keep its outputs trustworthy.

## The problem

Most BVLOS feasibility work happens in spreadsheets: one wind speed applied to
a flat total distance, one energy number checked against zero. That misses the
things that actually end flights — headwind on the outbound leg that a
tailwind home doesn't refund, rising terrain under a "constant altitude"
route, a geofence clipped by one leg, a return-to-home that is affordable at
waypoint 2 but not at waypoint 5.

bvlos-sim replaces that with a deterministic estimator over two YAML files: a
wind triangle solved per leg against a forecast grid, per-leg terrain from
SRTM, geometric intersection with real airspace polygons, an RTH reserve
check at every leg, and a fail-closed operational checklist over the result.
Deterministic means auditable: identical inputs produce byte-identical
canonical JSON, pinned by golden-fixture tests, so a verdict can be reproduced
and reviewed months later.

## Fail-closed, everywhere

The central design rule: **the tool never converts absence of evidence into
permission.**

- Checklist categories that were never evaluated read `◌ N/A` and block `GO`.
- A weather limit without a data source (`max_gust_mps` with no gust
  provider) makes the mission infeasible instead of silently passing.
- SORA mitigation declarations without assessable criteria are rejected, not
  credited. Population density exactly on a band boundary lands in the
  stricter band.
- An impossible wind triangle, excessive crab angle, or unstable
  time-varying-wind solution fails the leg instead of extrapolating.
- Monte Carlo outputs are labeled diagnostics with conditional statistics —
  never an operational probability.

Two explicit, auditable opt-outs exist — and only these. The
`--engineering-only` flag trades the operational gate for a purely
computational verdict, and `constraints.accepted_warning_codes` lets a
mission accept named advisory warnings after review. In both cases the JSON
envelope still records the full structured readiness verdict, including what
was acknowledged.

## Scope — what a GO is and is not

The verdict is a deterministic planning gate over the modeled preflight
categories. It is **not** flight authorization and not a complete safety
case. It does not attest live NOTAM/traffic/Remote ID/U-space state,
source-data freshness, aircraft qualification, held-out flight validation, or
SITL/HITL conformance — and the SORA output is a pre-assessment aid, not a
certified determination.

Three practical consequences:

- **Data is yours.** Airspace, weather, terrain, and population come from
  static files you fetch and commit. A GO is only as current as those inputs.
- **Profiles are placeholders until calibrated.** Shipped vehicle profiles
  are not fitted to measured data. Use `validate` to measure model error on
  your aircraft and `calibrate` to close it before trusting absolute numbers.
- **No regulatory standing.** MIT-licensed, no warranty; use as an early,
  reproducible feasibility gate *before* regulator-facing tooling and flight
  testing.

Where bvlos-sim sits among drone tools: PX4/ArduPilot fly the aircraft, QGC
authors and uploads missions, Gazebo simulates physics, UTM tools handle the
operational ecosystem. bvlos-sim is the deterministic validation layer in
between — it imports and exports QGC plans and records SITL conformance
evidence, but replaces none of those tools.

## Modeling

Fidelity v1 (default): geodesic leg-to-leg transit, constant/layered/gridded
wind sampling, station-keep loiter for hover-capable vehicles, phase-based
energy (hover/climb/cruise/descent power), static geofence and landing-zone
checks. Fidelity v2 (opt-in) adds tangent turn arcs at heading changes and
fixed-wing circular loiter, rejecting corners that don't fit
(`INVALID_GEOMETRY`) rather than clamping. Straight-leg sub-segment sampling
is an independent option in both modes.

The scenario runner builds a deterministic timeline over the estimate,
resolves events (lost link, wind change, landing zone loss) against it, and
evaluates policies and assertions. It is not a physics simulator and does not
run an autopilot — that is what the SITL layer is for.

## Architecture

```text
schemas/                Pydantic input models (mission, vehicle, scenario, ...)
estimator/core/         public enums, options, result models, typed errors
estimator/execution/    estimation, static checks, scenario runner
estimator/environment/  wind, terrain, population providers
estimator/math/         pure geometry: wind triangle, turn arcs, Dubins paths
adapters/               CLI, file loading, envelopes, report rendering
adapters/sitl/          ArduPilot adapter, evidence, comparison reports
```

Boundaries are rules, not conventions: domain logic never lives in CLI code,
`schemas/` never depends on execution internals, and simulator/MAVLink
imports are confined to `adapters/`. The stable Python surface is the
`estimator` package root; internal layout is free to change.

## Contracts

Every input schema and output envelope is versioned (`mission.v7`,
`estimator-envelope.v10`, …; `bvlos-sim schema-versions` prints the full set).
Within a published version: no field removals or renames, no enum or
exit-code meaning changes, no renderer-dependent verdicts, byte-stable
canonical JSON. Strict models reject unknown fields except in documented
free-form `metadata` maps. Golden fixtures pin representative outputs, and a
fixture diff is reviewed as a contract change, not snapshot churn.

Intentional changes bump the version and update fixtures, tests, and docs in
the same commit — the process is in
[CONTRIBUTING](https://github.com/Monotox/bvlos-sim/blob/main/CONTRIBUTING.md).
