# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning once public releases begin.

## [Unreleased]

### Added

- Initial `v0.2.0` release.
- Deterministic estimator v1 with fidelity v1 and fidelity v2 modes.
- Deterministic energy feasibility with reserve-at-landing outputs.
- Static GeoJSON geofence conflict checks.
- Static GeoJSON landing-zone reachability checks.
- Scenario runner with deterministic events, assertions, and comms-link lost-link policy outcomes.
- Layered altitude-band wind provider.
- Optional sub-segment wind sampling for long transit legs.
- Turn-arc dynamics in fidelity v2.
- Fixed-wing circular loiter in fidelity v2.
- Full YAML configurability for mission estimation and scenario initial conditions.
- Terrain-referenced altitude execution using an offline uniform elevation grid (`assets.terrain_file`).
- Spatiotemporal wind grid with quadrilinear interpolation (`assets.wind_grid_file`).
- Integrated example combining terrain, wind-grid, geofences, landing zones, energy, and fidelity v2.
- Dynamic landing-zone availability via scenario `landing_zone_unavailable` events; zones can be marked unavailable from a trigger point onward with `ALL_LANDING_ZONES_UNAVAILABLE` failure diagnostics.
- `LandingZoneEstimate.unavailable_zone_ids` and `LandingZoneStateReachability.available_zone_count` output fields for availability tracing.
- `lz_unavailability` parameter on `estimate_mission_distance_time` and `try_estimate_mission_distance_time` for library callers.
- Computed divert route estimates on `CommsLinkPolicyOutcome.divert_estimate` when a `lost_link` event fires with a `divert` policy and landing zones are configured; estimate includes geodesic distance, TAS-based transit time, cruise-power energy, reserve after divert, and feasibility flag.
- `DivertRouteEstimate` model exported from `estimator` package root.
- `estimator/execution/divert.py` with `compute_divert_estimate` as the deterministic divert route computation function.
