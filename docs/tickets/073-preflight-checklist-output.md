# Ticket 073: Pre-Flight Go/No-Go Checklist Output

## Goal

Add a `--format checklist` output mode to the `estimate` and `scenario`
commands that emits a structured, human-readable go/no-go checklist mapping
every feasibility result to a pass/fail line item. Drone operators review this
output in a terminal or paste it into a flight brief instead of parsing JSON.

## Motivation

A drone operator running a pre-flight estimate wants to know four things in
under 30 seconds:

1. Is the mission energy-feasible with sufficient reserve?
2. Is the route clear of geofence conflicts?
3. Is a divert landing zone reachable from every point?
4. Are there any advisory warnings?

Today the summary format (`--format summary`) answers question 1 with a
one-liner. The full JSON answers all four in 200+ lines. Neither is optimal
for a non-engineering ops reviewer in a safety-critical workflow.

`--format checklist` bridges this gap with a structured pass/fail list:

```
## Pre-Flight Checklist: pipeline_demo_001

✓ Energy feasibility     PASS   reserve 65.0 Wh above threshold (reserve at landing 585.0 Wh, threshold 225.0 Wh)
✓ Geofence clearance     PASS   0 conflicts across 2 zones
✓ Landing-zone coverage  PASS   reachable zone found at all 3 checked states
✗ Wind speed             WARN   max_wind_mps=3.7 ≤ constraint 10.0 mps — OK
  Advisory warnings      NONE

Status: GO
```

Or for a failed run:

```
## Pre-Flight Checklist: alpine_infeasible

✗ Energy feasibility     FAIL   reserve -210.0 Wh below threshold (reserve at landing 15.0 Wh, threshold 225.0 Wh)
✓ Geofence clearance     PASS   0 conflicts across 1 zone
✗ Landing-zone coverage  FAIL   no reachable zone at state 2/5
  Advisory warnings      2      MAX_WIND_EXCEEDED (leg 3), RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD

Status: NO-GO
```

The final `Status: GO / NO-GO` line makes the output machine-parseable
(`grep "^Status:"`) while remaining human-readable.

## Output Specification

One Markdown document with two sections.

### Header

```markdown
## Pre-Flight Checklist: <mission_id>
```

### Checklist Items

Each item follows the format:

```
<icon> <category>  <outcome>  <detail>
```

Where:
- `<icon>` is `✓` (pass), `✗` (fail), or `◌` (not checked / not applicable)
- `<category>` is left-padded to 25 characters for alignment
- `<outcome>` is `PASS`, `FAIL`, `WARN`, or `N/A`
- `<detail>` is a concise human sentence, never more than one line

### Checklist Categories

| Category | Source | Pass condition |
|----------|--------|----------------|
| Energy feasibility | `result.energy.is_feasible` | `True` |
| Geofence clearance | `result.geofence.is_feasible` | `True` |
| Landing-zone coverage | `result.landing_zone.is_feasible` | `True` |
| Resource availability | `result.resource.is_feasible` | `True` (if present) |
| Link availability | `result.link.is_feasible` | `True` (if present) |
| Advisory warnings | `result.warnings` | empty list |

Categories not present in the estimate are rendered with `◌` and outcome `N/A`.

### Status Line

```
Status: GO
```

or

```
Status: NO-GO
```

`GO` requires all present categories to be `PASS` or `N/A`, and
`Advisory warnings` to be empty or contain only `WARN`-level items.
Any `FAIL` → `NO-GO`.

## Implementation

### 1 — `adapters/checklist_markdown.py` (new)

```python
def render_checklist_markdown(envelope: EstimatorResultEnvelope) -> str:
    """Render a pre-flight go/no-go checklist as Markdown."""
```

Pure function, no external dependencies beyond the envelope.

### 2 — Extend `DocumentOutputFormat` / `OutputFormat`

Add `CHECKLIST = "checklist"` to the format enum and wire it into the
`estimate` and `scenario` render paths in `adapters/cli.py`.

### 3 — Tests

- `tests/test_checklist_markdown.py`:
  - `test_checklist_pass_all_shows_go`: envelope with all feasible → `Status: GO`
  - `test_checklist_energy_fail_shows_no_go`: energy infeasible → `Status: NO-GO`
  - `test_checklist_geofence_fail_shows_no_go`: geofence conflicts → `Status: NO-GO`
  - `test_checklist_missing_energy_shows_na`: no energy estimate → `◌ ... N/A`
  - `test_checklist_warnings_shows_count`: non-empty warnings list
  - `test_checklist_header_contains_mission_id`: `## Pre-Flight Checklist:` in output
  - CLI integration test: `estimate --format checklist` exits 0 and output
    contains `Status: GO`

### 4 — Documentation

Update `docs/USAGE.md` with a `--format checklist` section showing example
output for the success and infeasible demo missions.

## Integration

Reads only from `EstimatorResultEnvelope` fields already populated by the
estimator. No changes to core, schemas, or golden fixtures. Works with both
`estimate` and `scenario` commands because the scenario envelope embeds the
same `MissionEstimate`.

## Acceptance Criteria

- `estimate --format checklist` exits 0 on the success fixture.
- Output contains `Status: GO` for the success fixture.
- Output contains `Status: NO-GO` for the infeasible demo mission.
- Each check category renders with `✓`/`✗`/`◌` icon and outcome label.
- All existing estimate and scenario tests continue to pass.
