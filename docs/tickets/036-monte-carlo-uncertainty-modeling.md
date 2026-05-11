# Ticket 036: Monte Carlo Uncertainty Modeling

## Goal

Add an optional uncertainty-analysis layer around deterministic mission
estimation without changing deterministic default behavior.

## Current Gap

The estimator produces single deterministic outputs. It does not model input
uncertainty, run repeated samples, or report confidence intervals for mission
time, energy reserve, wind margins, or feasibility outcomes.

## Scope

- Define versioned uncertainty inputs for selected mission, vehicle, wind, and
  energy parameters.
- Add seeded Monte Carlo execution that wraps the deterministic estimator.
- Report distributions and summary statistics for key outputs.
- Preserve deterministic reproducibility for a given seed and sample count.
- Add CLI/API output contracts for uncertainty reports.
- Add tests for reproducibility, validation, and failure aggregation.

## Integration Requirements

- Add uncertainty configuration through YAML so users can pair it with existing
  mission, vehicle, terrain, wind-grid, geofence, landing-zone, and scenario
  files.
- Keep the deterministic `estimate` command as the baseline path and add
  uncertainty execution as an explicit opt-in mode or command option.
- Ensure scenario execution can reference uncertainty outputs only through a
  documented contract, without making ordinary scenarios nondeterministic.
- Add YAML examples for uncertainty runs that reuse existing mission, vehicle,
  terrain, and wind examples.
- Include uncertainty report output in JSON/Markdown rendering and fixture
  coverage if it becomes a public output surface.

## Acceptance Criteria

- A Monte Carlo run is reproducible with the same inputs and seed.
- The default estimator path remains deterministic and unchanged.
- Uncertainty outputs clearly distinguish sampled results from baseline
  deterministic estimates.
- Uncertainty runs compose with all implemented deterministic inputs instead of
  bypassing terrain, wind, geofence, landing-zone, or energy behavior.

## Out of Scope

- Real-time risk scoring.
- Regulatory approval calculations.
- Replacing deterministic feasibility checks.
