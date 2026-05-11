# Ticket 043: SITL Scenario Comparison Report

## Goal

Compare deterministic bvlos-sim scenario expectations against ArduPilot SITL
evidence and emit a versioned report that explains agreement, drift, and
unsupported comparisons.

## Current Gap

The project can define deterministic estimates and scenarios, and earlier SITL
tickets define adapter execution and evidence capture. There is still no
comparison layer that turns telemetry evidence into actionable validation
results.

## Scope

- Load the evidence bundle emitted by Ticket 042.
- Compare expected timeline, route phases, policy outcomes, command events, and
  selected kinematic metrics against observed SITL telemetry.
- Report pass/fail/unsupported/skipped comparison outcomes.
- Add tolerances and deterministic comparison rules.
- Emit canonical JSON and optional Markdown comparison reports.
- Add tests using synthetic evidence bundles.
- Document the distinction between SITL consistency checks and real-world
  validation.

## Integration Requirements

- Use deterministic `scenario` outputs as the expected behavior source.
- Reuse report/envelope conventions established by estimator, scenario, and
  uncertainty outputs.
- Keep comparison reports adapter-level; do not change core estimator result
  semantics solely for SITL.
- Ensure unsupported comparisons are explicit instead of silently omitted.
- Keep the path open for validation-track tickets 080-084 to reuse telemetry
  normalization concepts.

## Acceptance Criteria

- A deterministic scenario can be compared against a SITL evidence bundle.
- Comparison output identifies matched, missing, drifted, skipped, and
  unsupported observations.
- Reports are reproducible for a given evidence bundle and tolerance
  configuration.
- SITL comparison does not claim real-world calibration or operational approval.

## Out of Scope

- Real-world flight-log validation.
- Calibration profile fitting.
- Regulatory compliance scoring.
- Live UTM, Remote ID, or traffic integrations.
