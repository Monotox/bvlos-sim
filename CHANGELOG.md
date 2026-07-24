# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning once public releases begin.

## [Unreleased]

### Changed

- Output envelopes are now `estimator-envelope.v10`. `provenance.inputs` gains
  a `calibration` entry, so a run made under `--calibration` no longer has
  byte-identical provenance to the base vehicle it overrode.
  `input_schema_versions` gains `obstacles` and `calibration`, and `population`
  is corrected to `population-grid.v2` — the only version the loader accepts.
  `schema-versions` prints the same set.

### Added

- The ground-risk report now states its SORA version, the population assessment
  buffer, and the numerical dilation that was applied. When the buffer is zero
  the report carries an explicit **"Centerline-only figure — not a SORA iGRC"**
  warning: density sampled along the centerline understates the operational
  volume, and on the same route can report a materially lower iGRC than the
  buffered assessment. Previously the unqualified number was rendered as
  "Mission iGRC" with nothing to distinguish the two.
- Regression tests pinning four safety margins that no test previously
  protected. Each was verified by deleting the term and confirming the whole
  suite still passed: the obstacle `uncertainty_m` contribution to required
  clearance, the half-sample-gap dilation of the ground-risk population query
  radius, the half-sample-gap widening of the landing-zone distance check, and
  the RTH abort when return groundspeed falls between zero and
  `min_groundspeed_mps`. Every one of these only ever makes a verdict *more*
  permissive when removed, so they were the likeliest source of a future silent
  false `GO`.

### Fixed

- The SORA report now carries provenance. `render_sora_markdown` discarded
  everything but the assessment, so the filed artifact named neither the tool
  version, the SORA edition, the population data vintage, nor the input
  digests. The SORA envelope also omitted the terrain asset that gates the
  maximum-AGL verification, so the assessment was not reproducible from its own
  provenance.
- A batch no longer discards every completed run when one run cannot load.
  Missions are preloaded to enumerate their assets, so a single unreadable
  mission aborted the batch before any run executed. The failing run is now an
  `ERROR` row naming both the run id and the file, and the exit code still
  follows the documented contract.
- A leftover atomic-write temp file no longer blocks a rerun into the same
  `--output-dir`. An interrupted run left `.<name>.<rand>.tmp` behind, which the
  directory guard treated as a foreign file forever; the tool's own scratch
  files are now cleaned up.
- `migrate` exits `13` with a message instead of a bare traceback on an
  unexpected error, and rejects a non-string `airspace.class` as invalid input
  (`11`) rather than raising `TypeError`.
- `dt_s` is bounded below, so a tiny propagation step can no longer make the
  timeline consume unbounded time and memory.
- A centerline-only ground-risk assessment no longer satisfies the `GO` gate.
  The readiness check only rejected `mission_igrc > 7` and never looked at
  `population_assessment_buffer_m`, which is `0.0` whenever the mission omits
  the optional footprint block — so a figure that says nothing about the
  operational volume counted as ground-risk evidence. An unbuffered assessment
  is now reported as `ground_risk_footprint` missing evidence, matching the
  report warning added alongside it.
- A `landing_zone_unavailable` event naming a zone that is not configured now
  fails closed. The schedule was built from the declared ids without checking
  them against the loaded zones, so a stale or misspelled id removed nothing:
  the re-estimate came back bit-identical to the unperturbed mission, the
  contingency was never exercised, and the report echoed the id back as taken
  out of service. Unmatched ids now produce
  `UNKNOWN_LANDING_ZONE_REFERENCE` on the estimate.
- Divert feasibility now applies the gates and costs the rest of the estimator
  already does. `compute_divert_estimate` was the only wind-aware solver that
  never gated its wind triangle, so a divert needing a 70.8° crab against a 35°
  vehicle limit, or crawling at 2 m/s against a 3 m/s minimum, was reported
  feasible; both gates now fire. Divert energy also charged horizontal transit
  only — the target zone's `altitude_amsl_m` was never read — so descending
  400 m to the landing surface cost nothing; the terminal descent is now
  budgeted, and an unknown surface altitude fails closed exactly as
  landing-zone reachability already does. Finally the whole Dubins path was
  charged at the single straight-line bearing's groundspeed, understating any
  divert whose entry arc turns into wind; the path is now bounded by the
  harshest heading the turn sweeps, which is conservative by construction.
- Obstacle clearance no longer misses three whole categories of conflict.
  Proximity was decided by intersecting the route line with the obstacle
  footprint, which is empty unless the geometries actually cross: a zero-radius
  point obstacle under the default (unset) `min_obstacle_clearance_m` was
  invisible, and a purely vertical leg — every `vtol_takeoff`, vertical landing,
  and vertical-completion tail — built a zero-length line that intersects
  nothing, so a 75 m mast 18 m from the pad reported feasible. Proximity is now
  a distance test. Vertical clearance also re-derived altitude linearly between
  samples, which sits *above* the flown profile inside the segment holding the
  climb/descent kink and overstated height by up to 25 m; it now takes the
  conservative lower endpoint, as the terrain check already did.
- Vacuous obstacle evidence no longer reads as proven-clear. Two new blocking
  advisory warnings mirror `GEOFENCE_ZERO_ZONES`: `OBSTACLE_ZERO_FEATURES` when
  a configured obstacle file yields no obstacles (exactly what
  `scripts/fetch_obstacles.py` writes when Overpass returns nothing), and
  `OBSTACLE_KEEP_OUT_NOT_CONFIGURED` when every obstacle has zero radius and
  uncertainty and no clearance is configured, so the keep-out volume has no
  width.
- Declaring any resource system no longer voids `usable_capacity_curve`
  derating. A non-empty `vehicle.resource_systems` hands both the battery gate
  and the RTH gate to `resource_link.py`, which budgeted against the nameplate
  pack — so the moment an operator declared a resource system, the derating
  curve stopped derating anything. A 170 Wh pack that can only deliver 93.5 Wh
  was budgeted at 170 Wh, turning `INFEASIBLE / RTH_RESERVE_BELOW_THRESHOLD`
  into `SUCCESS` with RTH reported feasible. Resource capacity is now derated
  (including a pack declared on the resource system itself), while the reserve
  threshold stays sized on rated capacity so a derated aircraft is not easier to
  clear than a healthy one.
- Wind limits are now evaluated over each leg's full duration and altitude band.
  A leg's stored wind comes from the horizontal integration, whose elapsed time
  runs out early whenever the climb or descent outlasts the ground track — an
  ordinary close-but-much-higher waypoint. The altitudes past that point were
  never queried, and `_legs_with_weather_observations` trusted the stored value,
  so `max_wind_mps` and `max_crosswind_mps` were checked against the
  departure-end wind: a leg climbing into a 10 m/s band under an 8 m/s limit
  reported `success` at `worst_wind 2.0`. Each leg is now sampled across its
  whole span and the harsher of stored and sampled observation is used.
- Every surface that grades a scenario now publishes the same operational
  verdict, via a single `scenario_readiness()` helper. The verdict was computed
  in the envelope but recomputed — or ignored — everywhere else, so the same run
  could report `no_go` in JSON while the CLI exited `0` and the checklist printed
  `Status: GO`. Three surfaces were fail-open: the `scenario` exit gate graded
  `checklist_is_go(result.estimate)`, discarding the scenario's own evidence;
  `render_checklist_markdown_from_scenario` recomputed readiness from the
  estimate, so a **failed** assertion still printed `GO` on the card an operator
  signs; and batch `run_type: scenario` graded only `ScenarioStatus`, never
  consulting readiness at all — a mission the estimator called `INFEASIBLE` at
  −305 % reserve reported `PASSED` and exited `0`. `--engineering-only` was also
  never threaded into batch scenario/propagate dispatch, so those runs behaved as
  if it were permanently on; it is now honoured as the documented escape hatch.
- A scenario whose safety assertions never ran no longer reads as a verified
  contingency. `determine_scenario_status` only returns `FAILED` when an
  assertion actively fails, so `SKIPPED` and `UNSUPPORTED` outcomes left the
  scenario `PASSED` and contributed nothing to the readiness verdict. A
  `policy_divert_feasible` assertion — the tool's headline "inject a lost link
  and assert the divert still lands with reserve" check — is skipped whenever the
  event does not fire, the mission declares no `lost_link_policy`, or the policy
  action is not `divert`. A mission with no `lost_link_policy` therefore reported
  `PASSED` with the divert check silently unevaluated. Inconclusive assertions
  are now reported as `scenario_assertions` **missing evidence**, which blocks
  `GO` exactly like any other absent evidence. `evaluate_operational_readiness`
  gains an `additional_missing_evidence` parameter; scenario status and the
  result contract are unchanged.
- Geofence checks now follow the flown path instead of a planar endpoint chord.
  `_leg_geometry` built a two-point `LineString` in degree space with no
  densification and no longitude normalisation, while every other spatial check
  walks the leg geodesically via `route_leg_samples`. Three consequences, all
  silent: a 40 km leg at 60 °N bows ~54 m poleward of its chord, so a forbidden
  zone sitting in that gap was flown through and reported `conflicts: []`; a
  route leaving a ±30 m **required** corridor was reported fully covered; and a
  leg crossing the antimeridian produced a 359.98°-wide line that flagged a zone
  16 000 km away while missing one 500 m along the actual path. The check now
  builds each leg from the shared sampler — including materialized turn arcs —
  unwraps longitudes so an antimeridian crossing stays continuous, and lifts
  zones onto the same axis. A route that cannot be sampled now fails closed with
  `INVALID_GEOMETRY` instead of silently passing.
- Out-of-window required geofence zones no longer gate the verdict. The active
  set was computed for the coverage union but the *unfiltered* list was passed to
  the altitude check, so a night-only low-ceiling required zone forced
  `ROUTE_EXITS_REQUIRED_ZONE` on a mid-afternoon flight. This was fail-safe in
  direction (false NO-GO) but the only workaround was hand-editing the
  authority's zone file, destroying the audit trail.
- The SORA route-AGL check no longer transposes latitude and longitude on
  materialized turn arcs. `path_coordinates` are stored `(lon, lat)` and consumed
  in that order everywhere else, but `_conservative_route_max_agl_m` unpacked
  them as `(lat, lon)`, matching only its fallback tuple. On a `fidelity: v2`
  route with a real turn, 18 of 20 terrain queries went to a different continent
  — aborting with "terrain coverage cannot prove maximum AGL" on a tight grid,
  or verifying height over the wrong ground on a wide one.
- Mixed climb/descent legs are no longer billed entirely at the vertical phase
  power. A route action that changes altitude while covering ground is now
  costed by phase time — the climb or descent portion at `climb_power_w` /
  `descent_power_w`, the remainder at `cruise_power_w` — and the leg reports the
  time-weighted effective power, so `energy_wh == power_w * time_s / 3600` still
  holds. Previously the sign of `vertical_delta_m` alone selected one power for
  the whole leg, which **understated** energy whenever `descent_power_w` was
  below cruise: on a 10 km leg ending one metre lower, supplying the documented
  optional `descent_power_w` cut reported mission energy by 36 % and turned
  `INFEASIBLE reserve −64.2 %` into `FEASIBLE reserve 66.5 %` on otherwise
  identical inputs. The same defect **overstated** energy on climb legs by up to
  2.2×, rejecting missions that were in fact feasible. Both directions are now
  correct; expect climb-heavy missions to report materially lower energy.
- Return-to-home and landing-zone divert margins now budget against the derated
  pack. `usable_capacity_curve` reached only the mission-level gate, leaving
  every contingency margin computed against nameplate `battery_capacity_wh` — a
  declared derating had literally no effect on the RTH timeline. A 300 Wh pack
  with a `0.55` curve reported a `+59.5 Wh` worst-case RTH margin where the
  derated arithmetic gives `−75.5 Wh`. Emergency-path sampling keeps its own
  100 m bound, so a coarser transit setting cannot coarsen contingency energy.

### Changed

- `max_segment_length_m` now defaults to `500.0` instead of being unset, and
  every straight leg is sampled at its sub-segment midpoints. Leaving it unset
  previously selected a zeroth-order rule that sampled the leg once at its
  **departure end**, so a leg flying into building wind was billed at the wind
  it left home in: measured 30 % low in energy and 33 % low in time on a 13.7 km
  leg through a routine gradient. Legs shorter than the interval still resolve
  to a single midpoint sample, and the 500 m default tracks 100 m sampling
  within 1 %. Estimates report `metadata.applied_default_max_segment_length_m`
  when the default was applied, mirroring the existing minimum-groundspeed
  metadata. This changes default numeric output: golden fixtures were
  regenerated, and wind-triangle failures now name the sub-segment that failed
  (`No wind-triangle solution in sub-segment 1/3`) with `segment_index` and
  `n_segments` context. Set `max_segment_length_m` explicitly to pin the
  integration interval.

### Added

- Machine-readable preflight validation report (Ticket 107). Every command with
  `--validate-only` (`estimate`, `scenario`, `sample`, `propagate`, `batch`,
  `sora`, `convert`, `export`) gains a `--validate-format json` opt-in that emits
  a `preflight-validation.v1` envelope: per-file ok/error with a stable failure
  `stage` (`schema`/`asset-load`/`reference`) and `code`, plus an overall `ok`
  flag, exiting `0` (all valid) or `11` (any failure). Validate-only now also
  loads referenced mission assets (geofence, landing-zone, terrain, population,
  obstacle, wind-grid), so a broken asset path fails preflight instead of at run
  time, and all asset failures are collected in one pass. `calibrate`, `compare`,
  and `size-battery` gain `--validate-only` for parity. Plain-text output stays
  the default; the envelope carries no wall clock and is deterministic.
- Machine-readable run progress for long commands (Ticket 106). `sample`,
  `propagate`, and `batch` can now stream structured JSONL progress so a
  non-interactive worker can show live progress instead of a flat "running"
  until exit. Two opt-in flags select it: `--progress-format jsonl` writes one
  compact JSON record per interval to stderr, and `--progress-file PATH` writes
  the same stream to a sidecar file. Each record is
  `{"event":"progress","command":...,"completed":...,"total":...,"elapsed_s":...}`
  with monotonically increasing `completed` and a guaranteed final record where
  `completed == total` (sample count for `sample`/`propagate`, run count for
  `batch`); `elapsed_s` is monotonic wall-clock. Progress is a stderr/sidecar
  side-channel only — it never appears in the `--output` stream, adds no schema
  or envelope version, and leaves the result envelope, deterministic results,
  and exit codes unchanged. Off by default: a run with no progress flag behaves
  byte-for-byte as before. A progress callback is threaded through
  `run_monte_carlo`, `run_stochastic_propagation`, and `run_batch_manifest`.
- Contract-version discovery command (Ticket 105). A new read-only `bvlos-sim
  schema-versions` command (alias `contracts`) prints the resolved `tool_version`
  plus every supported output-envelope and input-schema version as canonical JSON
  and exits `0` without loading any mission, vehicle, or asset file. A backend can
  call it at startup to pin and check contract compatibility instead of running a
  full job to read versions off an envelope. Every printed version is sourced from
  the same module constant the envelopes emit (a drift test asserts this), so the
  map cannot silently diverge from a real run. `--version` is unchanged.
- Atomic output writes and clean cancellation (Ticket 104). Every `--output`
  write and every on-disk artifact writer (flight trace, phase segments,
  validation report, calibration profile, SITL artifacts) now writes to a sibling
  temp file, `fsync`s, and `os.replace`s it onto the target, so a killed or
  interrupted run never leaves a truncated file — the destination is either the
  prior content or absent. A new `CliExitCode.CANCELLED` (`14`) is returned when a
  run receives `SIGTERM`/`SIGINT`, installed by the console-script entrypoint, in
  place of the shell defaults (`143`/`130`). The cancellation contract is
  documented in `docs/CLI_EXIT_CODES.md` and `docs/VERSIONING_POLICY.md`.
- Calibration profiles and parameter fitting (Ticket 083). A new `bvlos-sim
  calibrate VEHICLE TRACE [TRACE ...]` command fits a narrow set of vehicle
  performance parameters from observed flights and emits a versioned,
  deterministic `calibration-profile.v1` artifact that *layers on* a base vehicle
  (it references `base_vehicle_id`, never replacing the profile). It fits
  `cruise_speed_mps` (mean transit-phase groundspeed), `climb_rate_mps` /
  `descent_rate_mps` (mean vertical rate over climbing/descending records), and
  `max_station_keep_wind_mps` (strongest wind held against in loiter dwell),
  reusing Ticket 081 segmentation as the phase bridge and touching no core
  estimator formula. Each fitted record carries the value, observed range, sample
  spread, sample count, applicable conditions, and provenance (source trace IDs,
  validation-report links, tool version); parameters with no samples are reported
  in `notes`, never fabricated. Calibrations are opt-in everywhere via
  `--calibration PATH` on `estimate`, `scenario`, and `validate`: the apply seam
  overrides only the fitted fields on a re-validated vehicle copy, leaves behaviour
  unchanged when absent, and rejects a `base_vehicle_id` mismatch as invalid input.
  Output is a Markdown report or the `calibration-profile.v1` envelope
  (`--format json`); the fit is deterministic. New public API:
  `adapters.calibration.fit_calibration_profile`, `apply_calibration`,
  `load_and_apply_calibration`, `write_calibration_profile`,
  `load_calibration_profile`, `CalibrationInput`, `CalibrationMismatchError`. New
  schemas exported from `schemas`: `CalibrationProfile`, `CalibratedParameter`,
  `CalibratedParameterName`, `CalibrationProvenance`,
  `CALIBRATION_PROFILE_SCHEMA_VERSION`. Adds a worked example under
  `examples/calibration/`. Energy-coefficient fitting and online auto-tuning remain
  out of scope.

- Version bump and release tooling (Ticket 098). A new `bvlos-sim bump
  <major|minor|patch>` command performs a release-ready version bump atomically:
  it updates `pyproject.toml` and rolls `CHANGELOG.md` (renaming `[Unreleased]`
  to the dated release section and opening a fresh `[Unreleased]`), then prints
  the suggested `git tag`/`push` follow-ups without ever tagging, pushing, or
  publishing. `--dry-run` previews the edits without writing; `--check` (for CI)
  fails when `pyproject.toml` is behind the latest git tag, preventing the
  version drift seen before v0.32.0. Golden fixtures are now version-agnostic:
  `tool_version()` honours a `BVLOS_SIM_TOOL_VERSION` override that `conftest.py`
  pins to `0.0.0-test`, so a version bump no longer churns the 16 golden fixtures
  and a release can no longer break the golden suite. New module
  `adapters.release` exposes the reusable semver/changelog/consistency helpers.

- Predicted-vs-observed validation metrics (Ticket 082). The new `bvlos-sim
  validate MISSION VEHICLE TRACE` command compares a deterministic mission
  estimate against an observed flight trace (`flight-trace.v1` from flight-log
  ingestion). It segments the trace into flight phases and lines predicted legs
  up with observed segments on their shared estimator leg-phase, then reports
  predicted-vs-observed time, horizontal distance (WGS-84 geodesic), mean
  groundspeed, and reserve at landing — at mission and per-phase level, each with
  absolute and percent error. Observed phases with no estimator counterpart and
  missing observed fields are reported in `notes`, never silently dropped. Output
  is a Markdown report or the versioned `validation-report.v1` envelope
  (`--format json`); the comparison is deterministic. New public API:
  `adapters.validation.build_validation_report`, `write_validation_report`,
  `load_validation_report`. New schemas exported from `schemas`: `ValidationReport`,
  `MissionValidationMetrics`, `PhaseValidation`, `MetricComparison`,
  `VALIDATION_REPORT_SCHEMA_VERSION`. Adds an example flight log and ingested trace
  under `examples/flight_logs/`. No changes to existing estimate, scenario, SITL,
  or SORA surfaces.

- Flight phase segmentation (Ticket 081). A `NormalizedFlightTrace` can now be
  deterministically segmented into contiguous `PhaseSegment` blocks using a
  mode-first algorithm: ArduPilot flight mode strings (TAKEOFF, RTL, LAND, LOITER,
  etc.) are mapped directly to `TracePhase` values; records in AUTO/GUIDED mode or
  without mode data fall back to kinematic rules derived from vertical rate and
  groundspeed. A single-record smoothing pass absorbs sensor-noise blips. Each segment
  carries the nearest estimator `LegPhase` string where a mapping exists (takeoff →
  `vertical_takeoff`, transit → `transit`, loiter → `loiter_dwell`, landing →
  `landing_transit`, rtl → `rtl_transit`). Climb, descent, divert, and unknown have no
  estimator counterpart and report `estimator_leg_phase: null`. Segmentation metadata
  records the algorithm identifier, which trace fields were available, and how many
  records could not be classified. Public API:
  `adapters.phase_segmentation.segment_trace`, `write_phase_segments`,
  `load_phase_segments`. Kinematic thresholds
  (`CLIMB_VERT_RATE_MPS`, `LOITER_SPEED_MPS`, `TRANSIT_SPEED_MPS`) are exported for
  downstream calibration use. New schemas exported from `schemas` package root:
  `TracePhase`, `PhaseSegment`, `PhaseSegmentResult`, `SegmentationMetadata`,
  `PHASE_SEGMENT_SCHEMA_VERSION`. No changes to existing estimate, scenario, or SITL
  surfaces.

- Flight log ingestion and trace normalization (Ticket 080). ArduPilot DataFlash text
  (`.log`) files can now be ingested into a versioned `NormalizedFlightTrace` artifact
  (`flight-trace.v1`). The adapter extracts GPS position, groundspeed, ground course,
  battery voltage/current/remaining, flight mode, and EKF wind estimate (NKF6/XKF6),
  merges auxiliary channels into GPS records by carry-forward timestamp, and records
  parsing assumptions and missing fields in a `FlightTraceProvenance` block. Traces can
  optionally reference a paired mission and vehicle YAML via `FlightTraceMissionRef`.
  Public API: `adapters.flight_log.ingest_dataflash_log`, `write_flight_trace`,
  `load_flight_trace`. New schemas exported from `schemas` package root:
  `NormalizedFlightTrace`, `FlightTraceRecord`, `FlightTraceProvenance`,
  `FlightTraceMissionRef`, `FLIGHT_TRACE_SCHEMA_VERSION`. No changes to existing
  estimate, scenario, or SITL surfaces.

- SORA mitigation depth: the `sora` command now applies operator-declared ground-risk mitigations (M1 strategic, M2 impact reduction, M3 ERP) and a tactical air-risk mitigation, declared in an optional `sora` block on the mission. The assessment reports the full credit ladder (iGRC → credits → final GRC), the residual ARC, and both the intrinsic and mitigated SAIL. Mitigation/credit tables are versioned data keyed by SORA revision; an unrecognised version is reported with a `MITIGATION_VERSION_UNSUPPORTED` advisory and no credits are applied. With no `sora` block the result is unchanged. The output remains a pre-assessment aid, not a certified determination.

- Opt-in return-to-home reserve gate via `constraints.require_rth_reserve`, returning `RTH_RESERVE_BELOW_THRESHOLD` and a checklist `NO-GO` when a route leg cannot preserve reserve after RTH.

- Altitude-aware geofence bounds via GeoJSON `floor_m` and `ceiling_m` properties. Forbidden zones now require both horizontal intersection and altitude-band overlap, while required zones must contain the full leg altitude band.

## [0.32.0] - 2026-05-29

### Changed

- Moved SITL adapter modules into `adapters/sitl/` subpackage. Module paths
  changed: `adapters.ardupilot_sitl` → `adapters.sitl.ardupilot`,
  `adapters.sitl_evidence` → `adapters.sitl.evidence`,
  `adapters.sitl_comparison` → `adapters.sitl.comparison`, and so on for all
  18 SITL-related files. The public schema contracts and CLI behaviour are
  unchanged.

### Added

- Dubins path solver (`estimator.math.dubins`) for bank-angle-constrained 2D path planning; evaluates RS (right arc + straight) and LS (left arc + straight) path types with unconstrained exit heading.
- Divert route estimates now use Dubins path distance (bank-angle-constrained arc + straight) when entry heading and `vehicle.performance.turn_radius_m` are available, replacing the previous straight-line geodesic approximation. Falls back to straight-line when heading or turn radius is unavailable.
- Fidelity v2 now subtracts the tangent-point offset (`turn_radius_m * tan(|Δθ|/2)`) from `path_distance_m` of both transit legs adjacent to each TURN_ARC, so total path distance reflects the true Dubins-path length through waypoints.
- Takeoff and landing-transit legs now report `path_distance_m` equal to `vertical_distance_m` (3D slant path distance for purely vertical legs), replacing the previous value of zero.
- `DivertRouteEstimate.warnings` field added; `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` is emitted when the geodesic distance to the target zone exceeds 50 km and the planar East-North approximation may accumulate meaningful error.

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
- Monte Carlo uncertainty analysis via new `sample` CLI command and `run_monte_carlo` Python API; configurable via `uncertainty.v1` YAML with seeded reproducibility and per-parameter distributions (`normal`, `uniform`) for wind, cruise speed, cruise power, and battery capacity.
- `uncertainty-report.v1` JSON envelope and Markdown rendering for uncertainty run outputs.
- `MonteCarloResult` and `SampledOutputStats` result models exported from `estimator` package root.
- `UncertaintyPlan`, `UncertaintyParameters`, `NormalDistribution`, `UniformDistribution` schemas exported from `schemas` package root.
- Resource-system feasibility abstractions on vehicle YAML via `resource_systems`, including onboard battery, external power, hybrid, and reserved future resource kinds.
- Communication-link feasibility abstractions on mission and scenario YAML via `link_systems`, including direct radio, mesh, cellular, satellite, Starlink-class, and hybrid link families.
- `result.resource` and `result.link` outputs in estimator and scenario reports, with structured diagnostics for resource and link infeasibility.
- Scenario assertions for `estimate.resource.is_feasible` and `estimate.link.is_feasible`.
- Integrated resource/link examples combining terrain, wind-grid, geofence, landing-zone, fidelity v2, scenario policies, and existing CLI paths.
- `sitl-evidence.v1` evidence bundle schema for SITL adapter runs, including input artifacts, expected deterministic outputs, simulator metadata, and observed telemetry/command-log artifact references.
- Contract-only `sitl` CLI command that builds a no-op SITL evidence bundle from existing scenario YAML without launching a live simulator.
- ArduPilot SITL artifact recorder for telemetry, command logs, simulator events, and adapter events, with completed `sitl-evidence.v1` bundles when observed artifacts are present.
