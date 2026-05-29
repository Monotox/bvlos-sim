# Ticket 063 — Return-to-Home Reserve Check from Worst-Case Point

## Status: Implemented

## Problem

The current energy feasibility model computes reserve at the planned
landing point (the last route item). For real BVLOS approval a more
important question is: at every point along the route, does the vehicle
have enough battery to fly straight home AND land with reserve intact?

Today there is no way to answer "can I RTH from waypoint 5 with reserve?"
without manually running a scenario with a lost-link event. This is the
single most common pre-flight question asked by real operators.

## Acceptance Criteria

1. `EnergyEstimate` gains an optional `rth_reserve_timeline` field: a
   list of per-leg RTH margin values (energy remaining after hypothetical
   RTH from that leg's endpoint minus reserve threshold).
2. The RTH distance from each leg endpoint to `mission.planned_home` is
   computed geodesically (straight-line, same as landing-zone divert).
3. RTH energy uses TAS-based cruise-power calculation (same model as
   landing-zone divert; wind correction from Ticket 062 can be applied
   later).
4. `MissionEstimate` exposes a new `rth_is_feasible` boolean: true iff
   the vehicle can RTH from every leg with reserve intact.
5. The Markdown report includes an "RTH Reserve Timeline" table.
6. The GeoJSON export colours each leg by RTH margin (green/yellow/red).
7. At least 6 tests cover: feasible RTH at all legs, infeasible RTH at
   one intermediate leg, short mission that is always feasible,
   missing home position handling.
8. Existing tests are unaffected (opt-in; `rth_reserve_timeline` is
   None when not computed, i.e., when `mission.planned_home` is absent).

## Scope

- `estimator/core/results.py` — `EnergyEstimate.rth_reserve_timeline`
- `estimator/execution/energy.py` — RTH distance + energy per leg
- `adapters/markdown.py` — RTH section
- `adapters/geojson_export.py` — RTH margin layer
- `docs/USAGE.md` — document new output field
- `tests/test_estimator_energy.py` — new RTH tests

## Notes

- `planned_home` is always present in `MissionPlan`; the planned home
  position is the RTH destination.
- This feature directly replaces the need to run a full scenario just to
  answer "can I RTH at any point?"
