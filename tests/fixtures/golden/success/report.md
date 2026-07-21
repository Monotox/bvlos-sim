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
- Static landing-zone reachability uses geodesic-aware Dubins distance when entry heading and vehicle turn radius are known, otherwise straight-line geodesic distance; divert energy remains deterministic and TAS-only.
- Landing-zone v1 excludes terrain, obstacles, dynamic availability, suitability scoring, and comms dependency.
- Dynamic landing-zone availability is a scenario-only feature; availability changes are resolved deterministically against the scenario timeline and do not affect the estimate CLI.
- Divert route estimates use geodesic-aware Dubins path distance (bank-angle-constrained arc + straight sampled to target geometry boundary points) when entry heading and vehicle turn radius are known; otherwise straight-line geodesic distance. When a wind provider is configured, a wind-triangle correction is applied to the divert ground speed; without a wind provider, TAS is used and a DIVERT_ENERGY_TAS_ONLY warning is emitted.
- Monte Carlo uncertainty sampling uses a seeded pseudo-random number generator; results are reproducible for a given seed, sample count, and uncertainty parameters. Wind sampling overrides any mission wind provider with a ConstantWindProvider per sample.

## Provenance

- Estimator API: `estimator.try_estimate_mission_distance_time`
- mission: `yaml` sha256 `f51ebfee7ac0a53d5f1f010d15fbc838d171388865d762f3732fdb113963b445`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Estimate Summary

- Horizontal distance m: `707.06`
- Vertical distance m: `240.00`
- Path distance m: `787.06`
- Time: `2m 49s (169.82 s)`
- Legs: `5`

## Leg Breakdown

| # | ID | Action | Dist m | Time s | Alt m | GS m/s | Wind m/s | Energy Wh |
|---|-----|--------|-------:|-------:|------:|-------:|---------:|----------:|
| 0 | takeoff | vtol_takeoff | 80.00 | 26.67 | 92.00 | — | — | 11.11 |
| 1 | wp1 | waypoint | 176.77 | 13.33 | 132.00 | 18.00 | 0.00 | 5.56 |
| 2 | loiter | loiter_time | 176.76 | 9.82 | 132.00 | 18.00 | 0.00 | 1.23 |
| 3 | loiter | loiter_time | 0.00 | 60.00 | 132.00 | — | 0.00 | 20.00 |
| 4 | rtl | rtl | 353.53 | 60.00 | 12.00 | 18.00 | 0.00 | 7.50 |

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `45.39`
- Battery capacity Wh: `900.00`
- Usable energy Wh: `675.00`
- Reserve threshold percent: `25.00`
- Reserve threshold Wh: `225.00`
- Reserve at landing Wh: `854.61`
- Reserve at landing percent: `94.96`
- Energy legs: `5`
- RTH feasible: `true`

## RTH Reserve Timeline

| Leg | ID | RTH Distance m | RTH Energy Wh | Reserve After RTH Wh | Margin Wh | Feasible |
|----:|----|---------------:|--------------:|---------------------:|----------:|----------|
| 0 | takeoff | 0.00 | 5.00 | 883.89 | 658.89 | true |
| 1 | wp1 | 496.09 | 10.95 | 872.39 | 647.39 | true |
| 2 | loiter | 640.46 | 11.95 | 870.16 | 645.16 | true |
| 3 | loiter | 353.53 | 9.96 | 852.15 | 627.15 | true |
| 4 | rtl | 0.00 | 0.00 | 854.61 | 629.61 | true |

## Warnings

- `LOITER_ASSUMED_ZERO_GROUND_DISTANCE` (leg 3): Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.
