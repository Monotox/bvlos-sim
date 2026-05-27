# Ticket 077: Mission Comparison Report

## Goal

Add a `bvlos-sim diff` command (or `bvlos-sim compare --estimate`) that runs
two estimate pairs side-by-side and emits a structured comparison: which mission
is shorter, which uses less energy, which has a better reserve margin, and what
changed between them. Useful for evaluating route alternatives or before/after
vehicle upgrades.

## Motivation

A drone operator comparing two route options today must run `estimate` twice,
note down both results, and mentally compare them. When the routes differ only
in one waypoint, the difference in reserve margin is easy to miss.

`bvlos-sim diff` answers "which route is better?" in one command:

```
$ bvlos-sim diff \
    route_a.yaml quadplane_v1.yaml \
    route_b.yaml quadplane_v1.yaml \
    --format summary

route_a.yaml vs route_b.yaml

  distance   A: 4 823 m   B: 5 241 m   Δ +418 m   (+8.7%)
  flight     A: 4m 49s    B: 5m 13s    Δ +0m 24s  (+8.3%)
  reserve    A: +281.6%   B: +263.1%   Δ −18.5 pp
  status     A: FEASIBLE  B: FEASIBLE
  warnings   A: 2         B: 3

Recommendation: A — shorter by 418 m, 18.5 pp better reserve margin
```

## Inputs

```
bvlos-sim diff <mission_a> <vehicle_a> <mission_b> <vehicle_b>
    [--format summary|json|markdown]
    [--output FILE]
```

Both missions are loaded and estimated independently using the same asset-loading
pipeline as `estimate`. Each may specify its own wind grid, terrain, and geofences
via its `assets:` block.

## Output Schema: `estimate-comparison.v1`

```json
{
  "schema_version": "estimate-comparison.v1",
  "tool_version": "...",
  "a": {
    "mission_id": "route_a",
    "status": "FEASIBLE",
    "total_path_distance_m": 4823.0,
    "total_time_s": 289.0,
    "reserve_at_landing_percent": 281.6,
    "reserve_at_landing_wh": 2533.0,
    "warning_count": 2,
    "failure_code": null
  },
  "b": {
    "mission_id": "route_b",
    "status": "FEASIBLE",
    "total_path_distance_m": 5241.0,
    "total_time_s": 313.0,
    "reserve_at_landing_percent": 263.1,
    "reserve_at_landing_wh": 2367.0,
    "warning_count": 3,
    "failure_code": null
  },
  "delta": {
    "distance_m": 418.0,
    "distance_percent": 8.7,
    "time_s": 24.0,
    "time_percent": 8.3,
    "reserve_percent_pp": -18.5,
    "reserve_wh": -166.0
  },
  "recommendation": "a",
  "recommendation_reason": "shorter route and higher reserve margin",
  "provenance": { ... }
}
```

`recommendation` is `"a"`, `"b"`, or `"none"` (when both are infeasible or
tied). The comparison is deterministic and suitable for CI gates.

## Recommendation Logic

1. If only one is feasible, recommend that one.
2. If both feasible, recommend the one with higher `reserve_at_landing_percent`.
3. If both infeasible, recommend `"none"`.
4. If reserve margins are within 1 pp, pick the shorter route.

## Output Formats

- `json` — `estimate-comparison.v1` envelope (default)
- `markdown` — table as shown in the motivation section
- `summary` — single line:
  `A: FEASIBLE +281.6%  B: FEASIBLE +263.1%  Δdist +418m  Δreserve −18.5pp  → A`

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | Both feasible |
| 1    | A feasible, B infeasible |
| 2    | B feasible, A infeasible |
| 10   | Both infeasible |
| 11   | Invalid input |
| 13   | Internal error |

## Implementation Approach

- New module: `estimator/execution/comparison.py` — `compare_estimates` takes
  two `MissionEstimate` objects and returns a `MissionComparisonResult`
- New adapter: `adapters/comparison_envelope.py` — `estimate-comparison.v1`
  schema, `build_comparison_envelope`, `render_comparison_markdown`
- New CLI command: `diff` registered on `app`; runs two full `_populate_mission_assets` +
  `try_estimate_mission_distance_time` pipelines and passes results to comparison
- Summary format added to `adapters/summary.py` as `format_comparison_summary`

## Files to Create or Modify

| File | Change |
|------|--------|
| `estimator/execution/comparison.py` | New — delta computation and recommendation |
| `adapters/comparison_envelope.py` | New — schema, JSON, Markdown, summary |
| `adapters/cli.py` | Add `diff` command |
| `adapters/summary.py` | Add `format_comparison_summary` |
| `tests/test_mission_comparison.py` | Acceptance tests |
| `docs/USAGE.md` | Document `diff` command |
| `docs/tickets/README.md` | Mark implemented when done |

## Acceptance Criteria

1. `bvlos-sim diff route_a.yaml vehicle.yaml route_b.yaml vehicle.yaml`
   exits 0 when both are feasible, 10 when both are infeasible.
2. `--format summary` outputs a single line with status, reserve, and
   recommendation for both sides.
3. Delta fields are correctly computed: `delta.distance_m = b.distance - a.distance`,
   positive means B is longer.
4. When A is feasible and B is infeasible, exit code is 1.
5. `--format json` validates against `estimate-comparison.v1`.
6. Using the same mission and vehicle for both A and B produces all-zero deltas
   and `recommendation: "none"` (tied).
7. Golden fixture test with pipeline_demo_001 against real_world/alpine_mission.
