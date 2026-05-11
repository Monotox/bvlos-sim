# Ticket 081: Flight Phase Segmentation

## Goal

Split real flight traces into the same kinds of phases the simulator models so calibration can happen per phase instead of only on total mission time.

## Current Gap

There is no segmentation layer to map raw/normalized flight traces into takeoff, climb, transit, loiter, descent, landing, RTL, or divert phases.

## Scope

- Add deterministic phase segmentation over normalized traces.
- Support initial v1 phase set:
  - takeoff
  - climb
  - transit
  - loiter
  - descent
  - landing
  - rtl
  - divert
- Emit segment boundaries and segment metadata.
- Record uncertain/unsegmentable portions explicitly instead of guessing.

## Integration Requirements

- Segment labels should map to existing estimator leg phases and mission actions
  wherever possible.
- Segmentation inputs must use normalized traces from Ticket 080 and retain
  links to mission, vehicle, terrain, wind, and scenario artifacts.
- Add examples that compare segmented observed phases with estimator/scenario
  phase outputs.
- Keep segmentation deterministic and replayable from stored YAML/JSON
  artifacts.

## Acceptance Criteria

- A normalized flight trace can be segmented deterministically into supported phases.
- Unknown/ambiguous segments are reported explicitly.
- Segmented phases can be compared against existing estimator legs and scenario
  timelines.

## Out of Scope

- Parameter fitting.
- Probabilistic segmentation.
