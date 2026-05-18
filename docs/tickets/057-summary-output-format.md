# Ticket 057: Summary Output Format

## Goal

Add `--format summary` to the `estimate` and `scenario` CLI commands, printing
exactly five lines of human-readable output. The summary is suitable for a
shell script, a pre-flight checklist, a CI gate, or a terminal that has no
room for a full Markdown report.

## Motivation

The Markdown renderer is comprehensive but verbose — full timeline, all leg
fields, per-phase energy breakdown. In a pre-flight context or a shell pipeline
the operator needs one glance: go / no-go, reserve margin, flight time, worst
wind margin, and the first failing check if any. No new computation is needed;
the summary is a terse projection of fields already present in
`MissionEstimate` and `ScenarioResult`.

## Output Specification

### `estimate --format summary`

```
FEASIBLE   reserve 38.2 %   flight 24m 13s   wind margin 3.1 m/s
```

Or on failure:

```
INFEASIBLE   reserve −12.4 %   flight 24m 13s   wind margin 3.1 m/s   [RESERVE_BELOW_THRESHOLD]
```

Fields in order:
1. `FEASIBLE` / `INFEASIBLE` / `ERROR`
2. `reserve <pct> %` — `(reserve_at_landing_wh / reserve_threshold_wh − 1) × 100`
   (negative means below threshold)
3. `flight <Xm Ys>` — `total_time_s` formatted as minutes and seconds
4. `wind margin <X> m/s` — smallest `(max_wind_speed_mps − actual_wind_mps)`
   across all legs; omitted when no wind model is active
5. `[FAILURE_CODE]` — the primary `FailureCode` name; omitted when feasible

Single line, space-separated. Machine-parseable with `awk '{print $2}'`.

### `scenario --format summary`

```
PASSED 3/3   reserve 38.2 %   flight 24m 13s   policy RTL
```

Or on assertion failure:

```
FAILED 2/3   reserve −4.1 %   flight 27m 08s   policy RTL   [ASSERTION: energy_at_divert_wh]
```

Fields in order:
1. `PASSED N/N` or `FAILED N/N` — passed/total assertions
2. Same `reserve`, `flight` fields as estimate summary
3. `policy <action>` — the triggered contingency policy action (`RTL`, `LAND`,
   `LOITER`, `DIVERT`, or `NONE`)
4. `[ASSERTION: <field_path>]` — first failing assertion's `field_path`;
   omitted when all pass

## Implementation Notes

The `--format summary` handler must live in a new function in the existing
adapter modules (`adapters/envelope.py` or a new `adapters/summary.py`), not
as logic in `adapters/cli.py`. The CLI handler calls the adapter function and
prints the returned string. This keeps the CLI thin and the summary format
independently testable.

Do not add a new `SummaryResult` schema or envelope. The summary is a
rendering of existing result types, not a new data model.

## File Plan

New files:

| File | Purpose |
|---|---|
| `adapters/summary.py` | `format_estimate_summary`, `format_scenario_summary` functions |
| `tests/test_summary_format.py` | Unit tests: feasible/infeasible/error cases, field values, single-line constraint |

Modified files:

- `adapters/cli.py` — add `summary` to `--format` choices for `estimate` and
  `scenario` commands; call `format_estimate_summary` / `format_scenario_summary`
- `adapters/__init__.py` — export new format functions

## Acceptance Criteria

1. `bvlos-sim estimate examples/missions/pipeline_demo_001.yaml
   examples/vehicles/quadplane_v1.yaml --format summary` exits 0 and prints
   exactly one line to stdout.
2. The line begins with `FEASIBLE` or `INFEASIBLE`.
3. `reserve` field is present and is a percentage value.
4. `flight` field is present and formatted as `<N>m <N>s`.
5. When infeasible, `[FAILURE_CODE]` is the last token and matches a
   `FailureCode` enum name.
6. `bvlos-sim scenario ... --format summary` exits 0 and prints one line
   beginning with `PASSED` or `FAILED`.
7. `--format json` and `--format markdown` are unchanged; all existing CLI
   tests pass.
8. `uv run ruff check` passes.

## Out of Scope

- Colour / ANSI escape codes — keep it plain text.
- Machine-readable key=value format — that is `--format json`.
- Summary mode for `sample` (Monte Carlo) or `propagate` (stochastic) — can
  follow as a trivial extension once the pattern is established.
