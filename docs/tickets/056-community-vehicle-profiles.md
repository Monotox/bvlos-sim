# Ticket 056: Community Vehicle Profiles

## Goal

Add five manufacturer-derived vehicle profiles to `examples/vehicles/community/`
covering real commercial UAS that operators and researchers are likely to
actually fly. Each profile is a YAML file with values sourced from published
spec sheets, peer-reviewed endurance studies, or manufacturer documentation,
with provenance links included as comments.

## Motivation

`quadplane_v1.yaml` is a placeholder with round-number guesses. A new user
confronted with it must replace every value before the tool means anything to
them. A `community/` directory with real aircraft profiles — "here is the DJI
Matrice 300 RTK, use it as-is or fork it" — transforms the first-run experience
from "fill in a spreadsheet" to "pick your aircraft and run." This is a content
gap, not a code gap. No new code is required.

## Target Profiles

### 1. DJI Matrice 300 RTK (`dji_matrice_300_rtk.yaml`)

- `vehicle_class: MULTIROTOR`
- Battery: 2× DJI TB60, 274.4 Wh each, 548.8 Wh combined
- Hover endurance: ~55 min published → hover power ≈ 598 W
- Max speed: 23 m/s; typical cruise: 12–15 m/s
- Max payload: 2.7 kg (affects power estimate)
- Source: DJI Matrice 300 RTK specs page + TB60 datasheet

### 2. Wingtra One Gen II (`wingtra_one_gen2.yaml`)

- `vehicle_class: VTOL`
- Battery: custom 97.2 Wh
- Cruise endurance: ~59 min at ~16 m/s cruise
- Stall speed: ~12 m/s; cruise altitude: typically 100–400 m AGL
- Source: Wingtra technical specifications

### 3. Quantum-Systems Trinity F90+ (`qs_trinity_f90_plus.yaml`)

- `vehicle_class: VTOL`
- Battery: 2× 99 Wh, 198 Wh combined
- Cruise endurance: ~90 min at ~18 m/s
- Payload: up to 800 g sensor bay
- Source: Quantum-Systems product page

### 4. Autel EVO Max 4T (`autel_evo_max_4t.yaml`)

- `vehicle_class: MULTIROTOR`
- Battery: Autel Smart Battery, 86.4 Wh
- Hover endurance: ~42 min → hover power ≈ 123 W
- Max speed: 20 m/s; typical cruise: 8–10 m/s
- Source: Autel EVO Max 4T specs page

### 5. Generic survey multirotor (`generic_survey_hexacopter.yaml`)

- Represents a mid-market 6 kg AUW survey hexacopter with a 30-min
  commercial payload mission profile.
- Values are typical-class estimates, clearly labelled as such.
- Useful as a conservative baseline when no specific aircraft is known.

## File Structure

```
examples/vehicles/community/
├── README.md
├── dji_matrice_300_rtk.yaml
├── wingtra_one_gen2.yaml
├── qs_trinity_f90_plus.yaml
├── autel_evo_max_4t.yaml
└── generic_survey_hexacopter.yaml
```

`README.md` must include:
- Source and provenance for each profile's key values
- Disclaimer: values are derived from published specs and should be validated
  against observed flight data before use in operational planning
- Instructions for forking a profile and calibrating it against real logs
  (cross-reference Tickets 080–082)

## Derivation Notes

For each profile, the following derivation is documented in the YAML as
comments:

- `hover_power_w`: derived from `battery_wh / hover_endurance_h`
- `cruise_power_w`: estimated from published cruise endurance if available;
  otherwise from `hover_power_w × 0.55` (typical fixed-pitch multirotor ratio)
- `reserve_threshold_wh`: set to 20 % of usable capacity (common operator
  policy; flagged as configurable)
- `turn_radius_m`: estimated from published bank angle limit and cruise speed
  via `v² / (g · tan(bank_rad))`

All derived values are marked `# derived` in the YAML. Directly published
values are marked `# source: <URL or document name>`.

## Acceptance Criteria

1. All five YAML files pass `VehicleProfile.model_validate()` without errors.
2. `uv run bvlos-sim estimate <mission-with-matching-vehicle_profile>.yaml
   examples/vehicles/community/<profile>.yaml` exits without schema errors for
   each profile (feasible or infeasible is acceptable).
3. `README.md` contains at least one provenance link per profile.
4. All existing tests continue to pass (no test imports community profiles).
5. `uv run ruff check` passes (no Python files added by this ticket).

## Out of Scope

- Calibrating profiles against real flight logs — that is Tickets 080–082.
- ArduPilot/PX4 parameter file cross-reference — deferred.
- Profiles for cargo UAS, tethered systems, or fixed-wing without VTOL —
  deferred to community contributions once the initial set ships.
