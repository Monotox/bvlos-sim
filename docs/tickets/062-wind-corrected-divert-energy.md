# Ticket 062 — Wind-Corrected Divert and Landing-Zone Energy

## Status: Implemented

## Problem

Historically, both the landing-zone reachability check
(`estimator/execution/landing_zone.py`) and the divert route estimate
(`estimator/execution/divert.py`) computed
energy cost as `cruise_power_w × (distance_m / tas_mps)` without wind
correction. In a 10 m/s headwind the actual ground speed can be half the
TAS, doubling the flight time and energy. This silently under-estimates
the divert energy, which can produce an `is_feasible=true` result for a
divert that would actually fail in a real headwind scenario.

Both functions carry docstring notes ("without wind correction") but
there is no warning emitted and no machine-readable flag in the output.

## Acceptance Criteria

1. `compute_divert_estimate` accepts the current wind vector at the
   action point and applies a wind-triangle correction to compute
   ground speed and energy.
2. Landing-zone reachability integrates the divert path through the active wind
   provider and includes terminal vertical energy to the landing surface.
3. Direct scenario divert routing preserves its explicit TAS-only compatibility
   path and warning when wind correction is not requested.
4. The divert energy field in `DivertRouteEstimate` is correctly higher
   in a headwind scenario and correctly lower in a tailwind scenario.
5. At least 4 new tests verify headwind, tailwind, crosswind, and
   no-wind cases.
6. The assumption text in the envelope ("TAS-based transit time without
   wind correction") is updated or removed for the affected code paths.

## Scope

- `estimator/execution/divert.py` — wind-corrected energy calculation
- `estimator/execution/landing_zone.py` — wind-corrected energy
- `estimator/core/scenario.py` — `DivertRouteEstimate` may need
  `wind_speed_mps` field for provenance
- `tests/test_divert_routing.py` — new wind-aware tests

## Notes

- The wind at the divert action point is available from the
  `EstimationContext.wind_provider`. The scenario runner needs to pass
  this through.
- Backwards compatibility: headwind cases will now show lower
  feasibility rates than before. Golden fixtures that involve divert
  scenario assertions may need regeneration.

## Completion

Scenario divert routing (`compute_divert_estimate`) and landing-zone
reachability both apply the wind-triangle correction: reachability delegates
to `estimate_emergency_path` in `energy.py`, which integrates the active wind
provider per segment (ground speed, not TAS) and adds terminal vertical energy
to the landing surface. Tests cover headwind, tailwind, crosswind, and no-wind
for both paths. The envelope assumption for landing-zone reachability, which
had still described the energy as TAS-only, now describes the wind-corrected
behaviour; the affected golden fixtures were regenerated. `DivertRouteEstimate`
records wind provenance negatively, through the presence of
`DIVERT_ENERGY_TAS_ONLY` when no wind was applied; a positive `wind_speed_mps`
field remains an optional future addition, deferred to avoid a
`scenario-report.v3` contract change for a value the warning already implies.
