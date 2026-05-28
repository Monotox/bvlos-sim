# Ticket 086: Stochastic Propagator Module Split

## Status

Implemented.

## Goal

Split `estimator/execution/propagator.py` into focused internal modules while
preserving the public `run_stochastic_propagation` behavior exactly.

## Motivation

The stochastic propagator has absorbed particle sampling, true-state tracking,
estimated-state tracking, closed-loop controller snapshots, timeline building,
summary statistics, and policy reserve calculations. That makes future work such
as stochastic GeoJSON export, progress feedback, and divert-route layers harder
to review safely.

This is too risky for a drive-by cleanup because stochastic outputs are
seed-sensitive and several tickets rely on exact reproducibility. The split
should be done as a dedicated behavior-preserving refactor with broad regression
coverage.

## Scope

Keep `estimator/execution/propagator.py` as the public facade for
`run_stochastic_propagation`, then move private implementation pieces into a
small package such as `estimator/execution/propagation/`:

| Module | Responsibility |
|--------|----------------|
| `curves.py` | Energy and position interpolation curves |
| `particles.py` | Particle track and population dataclasses |
| `sampling.py` | Sampled-parameter draws and particle creation |
| `timeline.py` | Timeline advancement and snapshot construction |
| `stats.py` | Sample statistics, rates, and reserve helpers |

The exact module names can differ if the implementation finds a clearer local
fit, but responsibilities should stay separated.

## Non-Goals

- Do not change stochastic schemas or envelope formats.
- Do not change CLI behavior, exit codes, or output rendering.
- Do not alter RNG draw order, seed handling, or floating-point operations.
- Do not rewrite the EKF or closed-loop controller logic.

## Files to Create or Modify

| File | Change |
|------|--------|
| `estimator/execution/propagator.py` | Reduce to facade/orchestration and imports |
| `estimator/execution/propagation/__init__.py` | New internal package marker |
| `estimator/execution/propagation/curves.py` | New curve helpers |
| `estimator/execution/propagation/particles.py` | New particle dataclasses |
| `estimator/execution/propagation/sampling.py` | New particle sampler helpers |
| `estimator/execution/propagation/timeline.py` | New timeline builder |
| `estimator/execution/propagation/stats.py` | New statistics helpers |
| `tests/test_stochastic_propagator.py` | Add exact-output regression coverage if needed |
| `tests/test_observation_model.py` | Confirm twin-state behavior remains unchanged |
| `docs/tickets/README.md` | Mark implemented when done |

## Acceptance Criteria

1. `run_stochastic_propagation` remains importable from the same module and has
   the same public signature.
2. Existing stochastic, observation-model, and closed-loop-control tests pass
   without fixture updates.
3. A same-seed stochastic run before and after the split produces identical
   `StochasticPropagationResult` values, including timelines and policy rates.
4. When `vehicle.sensors is None`, the no-sensor path remains bit-for-bit
   compatible with the current implementation.
5. New internal modules do not import CLI or adapter code.
6. The split leaves no module with mixed sampling, timeline rendering, and stats
   responsibilities.
