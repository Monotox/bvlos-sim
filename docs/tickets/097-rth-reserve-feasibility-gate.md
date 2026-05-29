# Ticket 097: Opt-in Return-to-Home Reserve Feasibility Gate

## Status

Planned.

## Goal

Allow a mission to declare that return-to-home (RTH) reserve must hold at every
leg, and have the estimator treat a violation as a first-class feasibility
failure — gating `status`, the CLI exit code, the JSON envelope diagnostics, the
checklist GO/NO-GO verdict, and the one-line summary — rather than the current
advisory-only treatment.

## Why This Is High Impact

Ticket 063 added the RTH reserve timeline and called it "the single most common
pre-flight question asked by real operators." Today it is computed but kept
purely advisory: a mission whose vehicle cannot fly home with reserve intact
from an intermediate leg still reports `FEASIBLE`, exits `0`, and shows
`Status: GO` on the checklist (with only an advisory RTH row). For an operator
filing a flight authorisation, "can I always get home with reserve?" is a hard
gate, not a footnote.

Making the gate **opt-in** via a mission constraint preserves the existing
advisory behaviour for everyone who does not set it (no golden-fixture churn,
no contract break) while letting safety-conscious operators get an honest
`NO-GO` and a non-zero exit code when RTH reserve cannot be guaranteed.

## Current gap

- `MissionEstimate.rth_is_feasible` exists but never influences `status`,
  `failure`, the exit code, or `checklist._is_go`.
- The advisory checklist row (added alongside this ticket's predecessor work)
  and the summary `RTH infeasible` field surface the condition but cannot flip
  the verdict, producing the confusing `RTH infeasible ... Status: GO` pairing
  for operators who actually require the gate.
- There is no `FailureCode` for an RTH reserve breach.

## Scope

### New schema field (`MissionConstraints`)

```yaml
constraints:
  min_landing_reserve_percent: 25.0
  require_rth_reserve: true   # new; default false (advisory-only, unchanged)
```

### New FailureCode

```python
RTH_RESERVE_BELOW_THRESHOLD = "RTH_RESERVE_BELOW_THRESHOLD"
```

### Enforcement logic

- When `constraints.require_rth_reserve` is true and an RTH reserve timeline is
  computed (i.e. `planned_home` is present), a timeline with any
  `is_feasible == False` point produces an `INFEASIBLE` result with
  `RTH_RESERVE_BELOW_THRESHOLD`, attributing the failure to the first failing
  leg (`leg_index`, `route_item_index`, `route_item_id`) with the margin in the
  failure context.
- When `require_rth_reserve` is false (default), behaviour is unchanged:
  the timeline is advisory and does not affect `status`.
- The check is provider-independent (it reuses the already-computed timeline) and
  deterministic.

### Output integration

- Add `RTH_RESERVE_BELOW_THRESHOLD` to `_STATIC_FEASIBILITY_FAILURE_CODES`
  handling in `adapters/envelope.py` so `result_validity` is computed correctly,
  and add an RTH field-path group so the failure maps to `result.energy`.
- `adapters/checklist_markdown.py`: when the gate is active, the RTH row becomes
  a real `✓ PASS` / `✗ FAIL` row and feeds `_is_go`; when inactive it remains
  the advisory `INFO` row. The summary keeps the `RTH infeasible` field.
- Add `estimate.energy.rth_is_feasible` (or `estimate.rth_is_feasible`) to
  `SUPPORTED_ASSERTION_FIELD_PATHS` and the scenario field resolvers.

### Files to create or modify

| File | Change |
|---|---|
| `schemas/mission.py` | Add `require_rth_reserve: bool = False` to `MissionConstraints` |
| `estimator/core/enums.py` | Add `RTH_RESERVE_BELOW_THRESHOLD` failure code |
| `estimator/execution/energy.py` | Emit RTH failure when the gate is active and a timeline point is infeasible |
| `estimator/execution/engine.py` | Thread the RTH failure into the result `status`/`failure` |
| `adapters/envelope.py` | Classify the new failure code; result-validity field paths |
| `adapters/checklist_markdown.py` | Make the RTH row gating when `require_rth_reserve` is set |
| `estimator/execution/scenario_assertions.py` | Add an `rth_is_feasible` resolver |
| `schemas/scenario.py` | Add the RTH path to `SUPPORTED_ASSERTION_FIELD_PATHS` |
| `tests/test_estimator_energy.py` | RTH gate feasible/infeasible/opt-out tests |
| `tests/test_checklist_markdown.py` | Gating row + GO/NO-GO tests |
| `docs/USAGE.md` | Document the opt-in gate and new failure code |

### Acceptance criteria

1. A mission with `constraints.require_rth_reserve: true` and a route where RTH
   reserve is breached at an intermediate leg returns `INFEASIBLE` with
   `RTH_RESERVE_BELOW_THRESHOLD` in the diagnostics, attributed to the first
   failing leg, and the CLI exits with the infeasible exit code.
2. The same mission with `require_rth_reserve` unset (or false) is unchanged:
   `status` is unaffected and the RTH row stays advisory `INFO`.
3. With the gate active, `--format checklist` shows `✗ RTH reserve FAIL` and
   `Status: NO-GO`; with a feasible RTH it shows `✓ PASS` and does not block GO.
4. `RTH_RESERVE_BELOW_THRESHOLD` appears in `estimator.FailureCode` public
   exports, and the RTH feasibility field is assertable from scenarios.
5. Existing golden fixtures are unchanged (the gate is opt-in and defaults off).
