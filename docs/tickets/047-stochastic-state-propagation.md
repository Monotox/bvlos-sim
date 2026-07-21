# Ticket 047: Stochastic State Propagation for Path-Dependent Risk

> Safety status: superseded by `stochastic.v2` / `stochastic-envelope.v2`.
> The v1 process-wind model and feasibility wording below are historical and
> must not be used. V2 is an open-loop diagnostic with conditional statistics.

## Goal

Add a time-stepped stochastic propagator that carries a belief state forward
through a full mission trajectory, accumulating correlated uncertainty across
legs and producing a time-series of per-step risk metrics — principally the
probability of reserve violation at any point mid-flight.

## Current Gap

`run_monte_carlo` runs N fully independent deterministic estimates with
perturbed scalar inputs. Each sample is a fresh deterministic execution: wind
estimation error from leg 2 does not carry into leg 3, and energy shortfalls
that compound across climb and cruise segments are invisible until the final
reserve check. The only risk output is a distribution over total-mission
scalars (`total_time_s`, `reserve_at_landing_wh`).

This means the simulator cannot produce the kind of probabilistic safety
evidence needed for BVLOS operational risk assessments: "what is the
probability the aircraft has insufficient reserve to reach its divert zone at
any point during the mission?" The Monte Carlo gives a spread over end-states;
it does not give path-dependent risk.

## Scope

- Define a `stochastic.v1` YAML input schema (`StochasticPropagationPlan`)
  that extends `uncertainty.v1` parameters with time-step configuration and
  process-noise settings.
- Add a `run_stochastic_propagation` execution path that propagates a belief
  state (position, energy, wind estimate) forward at configurable Δt using
  Gaussian (EKF-style) representation for MVP.
- Emit a `PropagationTimelinePoint` at each time step recording position
  statistics, energy distribution, and `p_reserve_violation`.
- Add a `propagate` CLI command producing a `stochastic-envelope.v1` JSON
  envelope and optional Markdown report.
- Preserve all existing deterministic and Monte Carlo interfaces; this is a
  new parallel execution mode.

## Belief State

At each time step `t` the propagator maintains a distribution over:

```
StateVector:
  lat                  float   # degrees
  lon                  float   # degrees
  alt_amsl_m           float   # metres
  energy_remaining_wh  float   # Wh
  wind_east_mps        float   # m/s — estimated, not true
  wind_north_mps       float   # m/s — estimated, not true
```

The initial distribution is constructed from `UncertaintyParameters` (reuse
existing schema). Wind state evolves with configurable process noise
(`wind_process_noise_std_mps`, default 0.5 m/s) at each step to model
temporal variability within the flight.

## New Public API

```python
def run_stochastic_propagation(
    plan: StochasticPropagationPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProviderProtocol | None = None,
) -> StochasticPropagationResult:
    ...
```

Exported from `estimator/__init__.py` alongside the existing
`run_monte_carlo`.

### `StochasticPropagationPlan` (`schemas/stochastic.py`, `stochastic.v1`)

```python
class StochasticPropagationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["stochastic.v1"]
    propagation_id: str
    mission_file: str
    vehicle_file: str
    dt_s: float = 1.0              # gt=0
    samples: int                   # ge=1
    seed: int
    wind_process_noise_std_mps: float = 0.5
    parameters: UncertaintyParameters  # reuse from schemas/uncertainty.py
```

### `StochasticPropagationResult` (`schemas/stochastic.py`)

```python
class PropagationTimelinePoint(BaseModel):
    elapsed_time_s: float
    lat_mean: float
    lon_mean: float
    energy_remaining_wh: SampleStats
    p_reserve_violation: float     # fraction of samples with reserve < threshold

class StochasticPropagationResult(BaseModel):
    propagation_id: str
    seed: int
    dt_s: float
    sample_count: int
    timeline: list[PropagationTimelinePoint]
    reserve_at_landing_wh: SampleStats | None
    feasibility_rate: float
    baseline: MissionEstimate
```

## CLI

New sub-command `propagate`:

```
bvlos-sim propagate stochastic.yaml [--dt 1.0] [--format json|markdown] [--output path]
```

Output schema: `stochastic-envelope.v1`. Exit codes follow the existing
`CliExitCode` convention.

## File Plan

New files:

| File | Purpose |
|---|---|
| `schemas/stochastic.py` | `StochasticPropagationPlan`, `StochasticPropagationResult`, `PropagationTimelinePoint` |
| `estimator/execution/propagator.py` | Core propagation loop |
| `estimator/execution/propagator_gaussian.py` | Gaussian belief representation |
| `adapters/stochastic_envelope.py` | JSON envelope builder, `STOCHASTIC_ENVELOPE_SCHEMA_VERSION` |
| `adapters/stochastic_markdown.py` | Markdown report renderer |
| `tests/test_stochastic_propagator.py` | Unit and integration tests |
| `examples/stochastic/pipeline_demo_001_stochastic.yaml` | Example plan |

Modified files:

- `estimator/__init__.py` — export `run_stochastic_propagation`, `StochasticPropagationPlan`, `StochasticPropagationResult`
- `adapters/cli.py` — add `propagate` command
- `schemas/__init__.py` — export new types

## Integration Requirements

- Reuse `UncertaintyParameters` and `SampleStats` from `schemas/uncertainty.py`
  so the initial distribution is configured identically to Monte Carlo inputs.
- Reuse `WindProviderProtocol` for wind sampling at each step; the propagator
  must compose with `LayeredWindProvider` and `SpatiotemporalWindProvider`.
- The `propagate` CLI must accept the same mission and vehicle YAML files
  as the `estimate` and `sample` commands.
- `run_stochastic_propagation` with `samples=1` and zero process noise must
  produce a final `energy_remaining_wh.mean` within 1 % of the deterministic
  baseline `reserve_at_landing_wh` (same physics, different execution path).

## Acceptance Criteria

1. `run_stochastic_propagation(samples=1, wind_process_noise_std_mps=0.0)`
   produces a `timeline[-1].energy_remaining_wh.mean` within 1 % of the
   deterministic baseline `reserve_at_landing_wh`.
2. `p_reserve_violation` is monotonically non-decreasing over the timeline.
3. `feasibility_rate` equals the fraction of samples ending with
   `energy_remaining_wh.mean >= reserve_threshold_wh`.
4. Same seed produces identical `StochasticPropagationResult` across two runs.
5. Different seeds produce different `p_reserve_violation` timeline values.
6. `propagate` CLI exits 0 on the example file; JSON output has
   `schema_version: "stochastic-envelope.v1"`.
7. All existing tests continue to pass.
8. `uv run ruff check` passes.

## Out of Scope (follow-on tickets)

- **Ticket 048**: Observation/update step — simulated GPS fixes and battery
  voltage measurements narrow the belief state mid-flight.
- **Ticket 049**: Particle filter representation replacing the Gaussian
  approximation for non-linear dynamics.
- **Ticket 050**: Contingency trigger probability — P(lost-link policy fires
  before waypoint N) derived from the stochastic propagation timeline.
- **Ticket 051**: Integration with SITL comparison pipeline — use replay
  telemetry to condition the belief state retrospectively.
