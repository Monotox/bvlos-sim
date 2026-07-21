# Community Vehicle Profiles

These profiles are starter configurations for common BVLOS survey aircraft.
They are intended for planning experiments, demos, and early estimator
calibration work. Treat every value as manufacturer-derived or typical-class
until it has been checked against observed flight logs from the exact aircraft,
payload, battery, firmware, and operating environment.

## DJI Matrice 300 RTK

`dji_matrice_300_rtk.yaml` models the DJI Matrice 300 RTK as a heavy
commercial quadrotor with two TB60 batteries and no payload installed in the
empty mass. The profile is useful for inspection, mapping, and public-safety
multirotor missions where hover and low-speed repositioning dominate.

Key specs:

- Vehicle class: `multirotor`
- MTOW: 9.0 kg
- Payload allowance: 2.7 kg
- Battery capacity: 548.8 Wh
- Cruise speed: 14.0 m/s
- Wind limit: 12.0 m/s

Primary provenance:

- https://www.dji.com/matrice-300/specs

Directly published values include MTOW, payload, maximum speed, climb/descent
rates, wind resistance, TB60 capacity, and hover endurance. Hover power is
derived from the published 55-minute endurance. Cruise and climb power are
engineering estimates and must be calibrated before operational use.

## Wingtra One Gen II

`wingtra_one_gen2.yaml` models the Wingtra One Gen II as a VTOL fixed-wing
mapping aircraft. It uses `vehicle_class: vtol` because takeoff, landing, and
transition phases need hover-speed and hover-power assumptions even though the
mission cruise phase behaves like a fixed-wing aircraft.

Key specs:

- Vehicle class: `vtol`
- MTOW: 4.5 kg
- Payload allowance: 0.8 kg
- Battery capacity: 97.2 Wh
- Cruise speed: 16.0 m/s
- Wind limit: 11.0 m/s

Primary provenance:

- https://wingtra.com/mapping-drone-wingtraone/

Directly published values include mass, payload, battery capacity, cruise
speed, endurance, and wind tolerance. Cruise power is derived from the
published 59-minute endurance. Hover, climb, descent, maximum speed, and turn
radius are estimates and should be replaced with aircraft-specific logs.

## Quantum-Systems Trinity F90+

`qs_trinity_f90_plus.yaml` models the Quantum-Systems Trinity F90+ as a VTOL
tiltrotor survey aircraft. It is suited to larger mapping routes where fixed-
wing cruise efficiency matters but VTOL launch and recovery are required.

Key specs:

- Vehicle class: `vtol`
- MTOW: 4.3 kg
- Payload allowance: 0.8 kg
- Battery capacity: 198.0 Wh
- Cruise speed: 18.0 m/s
- Wind limit: 12.0 m/s

Primary provenance:

- https://www.quantum-systems.com/trinity-f90/

Directly published values include mass, payload, cruise speed, maximum speed,
wind tolerance, battery capacity, and endurance. Cruise power is derived from
published 90-minute endurance. Hover, climb, descent, and turn-radius values
are estimates pending log-based calibration.

## Autel EVO Max 4T

`autel_evo_max_4t.yaml` models the Autel EVO Max 4T as an integrated-sensor
survey and inspection quadrotor. The profile keeps payload capacity modest
because the primary sensors are built into the aircraft.

Key specs:

- Vehicle class: `multirotor`
- MTOW: 2.05 kg
- Payload allowance: 0.3 kg
- Battery capacity: 86.4 Wh
- Cruise speed: 10.0 m/s
- Wind limit: 12.0 m/s

Primary provenance:

- https://www.autelrobotics.com/product/autel-evo-max-4t/

Directly published values include operational weight, maximum speed, climb and
descent rates, wind resistance, battery capacity, and hover endurance. Hover
power is derived from the published 42-minute endurance. Cruise and climb
power are estimates and need validation against real missions.

## Generic Survey Hexacopter

`generic_survey_hexacopter.yaml` is a conservative placeholder for a mid-
market six-arm survey multirotor at 6 kg AUW. Use it when the exact platform
has not been selected yet, or as a baseline for comparing measured aircraft
performance.

Key specs:

- Vehicle class: `multirotor`
- MTOW: 6.0 kg
- Payload allowance: 1.5 kg
- Battery capacity: 400.0 Wh
- Cruise speed: 12.0 m/s
- Wind limit: 10.0 m/s

Primary provenance:

- Typical-class estimate only; no manufacturer-specific source.

All values are placeholder estimates. The power model assumes a 30-minute
commercial mission class and fixed-pitch multirotor cruise power at 55% of
hover power. Replace all values with measured aircraft data before operational
use.

## Disclaimer

These profiles are not certified aircraft data, flight-safety approvals, or
operational limits. They are derived from published manufacturer
specifications, battery datasheets, and clearly marked engineering estimates.
Validate each profile against observed flight data before using it for
operational planning, safety cases, customer deliverables, or regulatory
evidence.

## Calibrating a Profile

Fork the closest YAML profile, then fly the aircraft over a known route with a
known payload, battery state, wind estimate, and reserve policy. Run the same
mission through `bvlos-sim estimate` and compare observed energy consumption,
flight time, climb segments, cruise legs, and reserve-at-landing against the
estimate output. Update `cruise_power_w`, `hover_power_w`, `climb_power_w`,
`cruise_speed_mps`, and turn-radius assumptions until the deterministic output
matches repeatable log evidence.

The `ingest-log`, `validate`, and `calibrate` commands automate this
comparison: ingest a flight log, validate predicted vs. observed metrics, and
fit a calibration profile (see `docs/cli.md`). Keep the original
manufacturer source link in `metadata.source`.
