# Ticket 065 — Geofence and Landing-Zone Awareness in Stochastic Propagation

> Safety status: superseded by the diagnostic v2 contract. The accounting
> invariant is `sample_count + infeasible_sample_count + failed_sample_count ==
> plan.samples`; `spatial_infeasible_count` is a subset of the infeasible count.

## Status: Implemented in diagnostic v2

## Historical Problem

`run_stochastic_propagation` passes `geofences` and `landing_zones`
to each particle's estimator call (they are propagated through
`_EstimatorInputs`), but the particle energy curve is derived from
the *nominal* route, not from a geofence-aware route. A particle whose
sampled parameters (e.g., wind) make the route geofence-infeasible is
silently dropped rather than counted as a feasibility failure.

Additionally, `feasibility_rate` currently only counts energy reserve
violations. A particle that cannot reach any landing zone at reserve
(due to wind pushing it off-route) is not reflected in `feasibility_rate`.

## Acceptance Criteria

1. Particles that fail the estimator due to a geofence conflict are
   counted as infeasible (not silently dropped) and reflected in
   `feasibility_rate`.
2. Particles that fail landing-zone reachability (if landing zones are
   provided) are counted as infeasible.
3. The `StochasticPropagationResult` gains a `dropped_sample_count`
   field indicating how many samples could not be evaluated at all
   (estimator error, not a feasibility check).
4. The stochastic envelope JSON includes `dropped_sample_count`.
5. The Markdown report includes a "Dropped Samples" row when > 0.
6. At least 3 new tests: geofence conflict inflates infeasibility rate,
   landing-zone unreachability inflates infeasibility rate, dropped
   samples are reported separately.

## Scope

- `estimator/execution/propagator.py` — distinguish dropped (error)
  from infeasible (geofence/lz) particles
- `schemas/stochastic.py` — `dropped_sample_count` field
- `adapters/stochastic_markdown.py` — dropped count row
- `adapters/stochastic_envelope.py` — pass through
- `tests/test_stochastic_propagator.py` — new tests

## Notes

- This ticket fixes the denominator-correctness issue for the spatial
  constraints path (the energy-only denominator bug was already fixed
  in a prior change).
- Backwards compatibility: `dropped_sample_count` defaults to 0 and
  the golden fixture is unaffected when no particles drop.
