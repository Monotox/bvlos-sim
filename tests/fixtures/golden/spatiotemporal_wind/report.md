# Estimator Report

- Status: `success`
- Envelope schema: `estimator-envelope.v9`
- Tool version: `0.0.0-test`

## Result Validity

- Complete: `true`
- Partial: `false`
- Valid for full mission: `true`
- Scope: `full_mission`

## Diagnostics

- `warning` `LOITER_ASSUMED_ZERO_GROUND_DISTANCE`: Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.

## Assumptions

- Estimator v1 is deterministic and uses no randomness.
- Wind input is constant in space and time unless a layered, time-varying, or spatiotemporal grid provider is used.
- Transit is modeled as geodesic leg-to-leg kinematics.
- Terrain-referenced altitude uses an offline uniform elevation grid; online terrain service calls are not performed.
- Fidelity v1 uses geodesic leg-to-leg kinematics with no turn-arc dynamics or sub-segment wind sampling; fidelity v2 replaces feasible corners with connected circular fillets, trims adjacent transit legs to their tangent points, and samples wind along the materialized path. Corners that cannot fit the configured turn radius fail closed.
- Fixed-wing circular loiter requires fidelity v2; it is unsupported in fidelity v1.
- Takeoff and landing-transit legs report path_distance_m equal to vertical_distance_m; for purely vertical movement this is the 3D slant path distance.
- Energy feasibility uses deterministic phase power values from the vehicle profile.
- Explicit resource systems are evaluated after route expansion; when configured, they determine resource feasibility while result.energy remains the legacy battery-only energy view. Onboard and hybrid resources include per-state RTH reserve demand; continuous external power replaces battery reserve gating but must cover RTH peak power.
- Communication-link feasibility is deterministic and uses configured static availability and range constraints only; live network calls are not performed.
- Static geofence feasibility uses the materialized 2D lon/lat flown path, including fidelity-v2 turn arcs; zones declaring floor_m/ceiling_m additionally constrain the leg's altitude band, treated as AMSL.
- Static landing-zone reachability uses geodesic-aware Dubins distance when entry heading and vehicle turn radius are known, otherwise straight-line geodesic distance; divert energy integrates the active wind provider through a per-segment wind-triangle ground speed and adds the terminal vertical energy to the landing-surface altitude.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use geodesic-aware Dubins path distance (bank-angle-constrained arc + straight sampled to target geometry boundary points) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. When a wind provider is configured, a wind-triangle correction is applied to the divert ground speed; without a wind provider, TAS is used and a DIVERT_ENERGY_TAS_ONLY warning is emitted.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `75f3cb60024d9376cce3bcfe1076cd9ed7dbc49f6986e54df094381e898df1d4`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`
- wind_grid: `yaml` sha256 `10326e2f5c6d70305d94bbd79e38824ea5fd8db0ed0d2cd056c6ce60dc9fc216`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.06`
- Vertical distance m: `240.00`
- Path distance m: `787.06`
- Time: `2m 49s (169.06 s)`
- Legs: `5`

## Leg Breakdown

| # | ID | Action | Dist m | Time s | Alt m | GS m/s | Wind m/s | Energy Wh |
|---|-----|--------|-------:|-------:|------:|-------:|---------:|----------:|
| 0 | takeoff | vtol_takeoff | 80.00 | 26.67 | 92.00 | — | — | 11.11 |
| 1 | wp1 | waypoint | 176.77 | 13.33 | 132.00 | 19.51 | 2.00 | 5.56 |
| 2 | loiter | loiter_time | 176.76 | 9.06 | 132.00 | 19.51 | 2.00 | 1.13 |
| 3 | loiter | loiter_time | 0.00 | 60.00 | 132.00 | — | 2.00 | 20.00 |
| 4 | rtl | rtl | 353.53 | 60.00 | 12.00 | 16.40 | 2.00 | 7.50 |

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `45.30`
- Battery capacity Wh: `900.00`
- Usable energy Wh: `675.00`
- Reserve threshold percent: `25.00`
- Reserve threshold Wh: `225.00`
- Reserve at landing Wh: `854.70`
- Reserve at landing percent: `94.97`
- Energy legs: `5`
- RTH feasible: `true`

## RTH Reserve Timeline

| Leg | ID | RTH Distance m | RTH Energy Wh | Reserve After RTH Wh | Margin Wh | Feasible |
|----:|----|---------------:|--------------:|---------------------:|----------:|----------|
| 0 | takeoff | 0.00 | 5.00 | 883.89 | 658.89 | true |
| 1 | wp1 | 496.09 | 11.08 | 872.25 | 647.25 | true |
| 2 | loiter | 640.46 | 12.20 | 870.00 | 645.00 | true |
| 3 | loiter | 353.53 | 10.19 | 852.01 | 627.01 | true |
| 4 | rtl | 0.00 | 0.00 | 854.70 | 629.70 | true |

## Weather Feasibility

- Feasible: `true`
- Checked legs: `5`
- Max wind m/s: `10.00`
- Max crosswind m/s: `—`
- Max gust m/s: `—`
- Worst wind m/s: `2.00`
- Worst crosswind m/s: `1.26`
- Violations: `0`

## Warnings

- `LOITER_ASSUMED_ZERO_GROUND_DISTANCE` (leg 3): Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.
