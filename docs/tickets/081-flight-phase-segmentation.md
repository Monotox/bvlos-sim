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

## Acceptance Criteria

- A normalized flight trace can be segmented deterministically into supported phases.
- Unknown/ambiguous segments are reported explicitly.

## Out of Scope

- Parameter fitting.
- Probabilistic segmentation.
