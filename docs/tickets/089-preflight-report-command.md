# Ticket 089: Preflight Report Command

## Status

Planned.

## Goal

Add a `preflight` CLI command that runs the full pre-departure validation
sequence — deterministic estimate, scenario policy check, and Monte Carlo risk
envelope — in a single invocation, producing a combined operator-ready report.
This is the primary user-facing workflow for a BVLOS operator preparing a
mission: today they must run three separate commands and manually synthesise
the results.

## Why This Matters

A first-time contributor or operator arriving at the repo sees three separate
commands: `estimate`, `scenario`, and `sample`. None of them alone answers the
question "is this mission ready to fly?". The operator has to:

1. `bvlos-sim estimate mission.yaml vehicle.yaml --format checklist` — static GO/NO-GO
2. `bvlos-sim scenario scenario.yaml --format summary` — lost-link policy check
3. `bvlos-sim sample uncertainty.yaml --format summary` — Monte Carlo reserve envelope

The `preflight` command collapses this into one invocation and one report that
is directly usable as a pre-departure briefing document.

## Scope

### CLI

```bash
bvlos-sim preflight mission.yaml vehicle.yaml scenario.yaml uncertainty.yaml \
  --format markdown \
  --output preflight_brief.md
```

All four inputs are positional. Scenario and uncertainty files are optional;
when omitted only the deterministic estimate section is included.

Supported `--format` values: `markdown`, `json`, `summary`.

`--format summary` produces a compact multi-line status block:
```
Estimate: GO   reserve 281.6 %   flight 2m 49s
Scenario: PASSED 5/5   policy DIVERT
Risk:     feasible 100%   reserve p5 823.9 Wh   p50 858.2 Wh   n=200
```

### Markdown report sections

1. **Mission Summary** — mission_id, vehicle_id, planned_home, departure time stamp
2. **Deterministic Estimate** — checklist table (energy, geofence, LZ, resource, link)
3. **Contingency Scenario** — scenario summary: events fired, policy action, assertion results
4. **Stochastic Risk** — p5/p50/p95 reserve, feasibility rate, failed and spatial-infeasible counts
5. **Advisory Warnings** — deduplicated warnings across all three runs
6. **Go/No-Go Decision** — overall `Status: GO` or `Status: NO-GO` with reason

The overall `Status: GO` requires:
- estimate: FEASIBLE (all feasibility checks pass)
- scenario: PASSED (all assertions pass, or no scenario provided)
- stochastic: feasibility_rate ≥ configured threshold (default 95%)

### JSON envelope

A new versioned schema `preflight-report.v1` embedding the three component
envelopes plus the overall go/no-go decision and merged warnings.

### `--validate-only`

Validates all four input files against their schemas without running the estimator.
When implemented, `--validate-only --validate-format json` should emit the
`preflight-validation.v1` envelope from Ticket 107 (`schemas/preflight_validation.py`)
rather than a bespoke format, so there is exactly one machine-readable preflight path.

## Composition

- Reuses `try_estimate_mission_distance_time`, `run_scenario`, and `run_monte_carlo` directly — no new execution paths.
- Checklist rendering from `adapters/checklist_markdown.py` is reused for the estimate section.
- Scenario and uncertainty envelopes are embedded verbatim in the JSON output.
- `--format geojson` and `--format kml` are out of scope; use `estimate --format geojson` separately.
- Exit codes follow the strictest of the three components: any NO-GO condition exits 10.

## Acceptance Criteria

- `bvlos-sim preflight mission.yaml vehicle.yaml --format summary` runs without scenario/uncertainty and reports the estimate-only status.
- `bvlos-sim preflight mission.yaml vehicle.yaml scenario.yaml uncertainty.yaml --format markdown` produces a Markdown report covering all four sections.
- `bvlos-sim preflight ... --format json` emits a valid `preflight-report.v1` JSON envelope.
- `bvlos-sim preflight ... --validate-only` validates all supplied files and exits 0/11.
- All existing tests continue to pass; new command adds ≥ 10 tests covering each format and the GO/NO-GO logic.
