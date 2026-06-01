# Ticket Backlog

**60 implemented · 18 planned · 1237 tests passing**

This directory tracks every capability from idea to implementation. Completed
tickets are kept as historical records. Open tickets describe what to build
next and why.

---

## What's already built

| Area | Tickets | Ships as |
|---|---|---|
| Core schemas & CLI | 001–003 | `estimate`, JSON envelopes, golden fixtures, public API |
| Energy & feasibility | 010–012, 061, 063, 097, 099 | Energy budget, mass/density/SoC energy fidelity, geofence (2D + altitude bounds), landing-zone reachability, RTH reserve timeline with opt-in feasibility gate |
| Scenario runner | 020–021, 069 | Lost-link policies, per-event contingency overrides, contingency events, assertions |
| Route physics | 030–039, 100 | Fidelity v2, layered/spatiotemporal wind, terrain alt, Dubins divert, obstacle and terrain clearance |
| SITL (ArduPilot) | 040–043 | `sitl` command, MAVLink upload, telemetry recording, `compare` |
| Stochastic propagation | 047–049, 086 | `propagate` command, twin-state EKF, closed-loop tracking controller; split into `propagation/` subpackage |
| Output formats | 055, 057, 072–075 | GeoJSON/KML exports, `summary`, `checklist`, `profile`, `sensitivity`, `size-battery` |
| Batch, import & export | 060, 085, 091 | `batch` command, `convert` QGC importer with `--vehicle-profile`, `--format csv`, `export` mission→QGC `.plan` writer |
| Real-world data | 052–053, 056, 059 | Fetch scripts, community vehicle profiles, infeasible Alpine demo |
| Regulatory pre-assessment | 094–095 | SORA Ground Risk Class (iGRC), Air Risk Class, and GRC×ARC→SAIL with applicable OSOs via the `sora` command |
| Weather & GO/NO-GO | 092–093 | Enforced `max_wind_mps`/`max_crosswind_mps` weather minimums with a checklist Weather-limits row; time-varying geofence activation windows |
| Correctness fixes | 062, 065 | Wind-triangle divert correction, stochastic spatial infeasibility tracking |
| Documentation | 096 | MkDocs Material site published to GitHub Pages, auto-built from `main` |
| Release tooling | 098 | `bump` command (semver bump + changelog roll + `--check` drift guard); version-agnostic golden fixtures |
| Calibration & validation | 080, 081, 082, 083 | `flight-trace.v1` ingestion, `phase-segments.v1` segmentation, `validation-report.v1` predicted-vs-observed metrics via the `validate` command, `calibration-profile.v1` parameter fitting via the `calibrate` command |

Full feature list: [`docs/tickets/README.md` implemented section](#implemented-tickets) · Test coverage: `uv run pytest`

---

## Planned work

Items are ordered by impact. Pick one, read its ticket file, open a PR.

### Quick wins

| # | Ticket | What it adds |
|---|---|---|
| 088 | [Performance benchmarks](./088-performance-benchmarking-and-regression-gates.md) | `pytest-benchmark` suite + CI regression gates (no production code changes) |
| 089 | [Preflight report command](./089-preflight-report-command.md) | Single `preflight` command combining estimate + scenario + Monte Carlo into one operator briefing |
| 090 | [Schema migration tooling](./090-schema-version-migration-tooling.md) | `bvlos-sim migrate` command to auto-upgrade YAML files when schema versions bump |

### Backend integration readiness

Gaps surfaced while reviewing whether the engine can be driven cleanly from a
long-running service (the Mission Control web backend) as a one-process-per-job
subprocess. None blocks single-shot CLI use; each sharpens the contract a queue
worker depends on.

| # | Ticket | What it adds |
|---|---|---|
| 105 | [Contract-version discovery command](./105-contract-version-discovery-command.md) | `schema-versions` command printing supported input/output contract versions without running a job |
| 106 | [Machine-readable run progress](./106-machine-readable-run-progress.md) | JSONL progress for `propagate`/`sample`/`batch` so a non-TTY worker can show live progress (extends 067) |
| 107 | [Machine-readable preflight report](./107-machine-readable-preflight-report.md) | JSON `--validate-only` envelope plus GeoJSON asset preflight across run types (composes with 089) |

### Core simulation gaps

| # | Ticket | What it adds |
|---|---|---|
| 062 | [LZ reachability wind correction](./062-wind-corrected-divert-energy.md) | Apply wind-triangle correction to landing-zone reachability energy (divert already done) |
| 064 | [Batch scenario & propagate](./064-batch-scenario-and-propagate.md) | Extend `batch` command to run scenario and propagate jobs, not only estimates |

### Output & visualisation gaps

| # | Ticket | What it adds |
|---|---|---|
| 076 | [Departure window finder](./076-departure-window-finder.md) | Scan a forecast window for the first feasible departure time |
| 077 | [Mission comparison report](./077-mission-comparison-report.md) | Side-by-side `diff` of two mission estimates |
| 066 | [Stochastic GeoJSON export](./066-stochastic-geojson-export.md) | `--format geojson/kml` for `propagate` command |
| 067 | [Propagation progress feedback](./067-propagation-progress-feedback.md) | Progress bar / stderr updates during long particle runs |
| 068 | [Divert route GeoJSON layer](./068-divert-route-geojson-layer.md) | Add computed divert paths as a separate layer in scenario GeoJSON/KML |

### Hardware validation ladder

| # | Ticket | What it adds |
|---|---|---|
| 045 | [PX4 SITL — launch & upload](./045-px4-sitl-launch-and-mission-upload.md) | PX4 SITL adapter behind the existing evidence contract |
| 046 | [PX4 SITL — telemetry & evidence](./046-px4-sitl-telemetry-recorder-and-evidence-bundle.md) | PX4 artifact recording and evidence bundle assembly |
| 087 | [HITL adapter](./087-hardware-in-the-loop-hitl-adapter.md) | Real flight controller hardware (Pixhawk) in the validation loop |

### Integrations & platform

| # | Ticket | What it adds |
|---|---|---|
| 054 | [Reference calibration inputs](./054-reference-inputs-for-calibration-and-import.md) | Curated reference datasets for model calibration and import |
| 058 | [NOTAM / live airspace](./058-notam-live-airspace-integration.md) | Dynamic no-fly zone ingestion from live NOTAM feeds |
| 050 | [REST API & web UI](./050-user-interfaces-and-service-adapters.md) | HTTP service wrapper and browser-based preflight interface |
| 070 | [Operational integration seams](./070-operational-integration-seams.md) | Hooks for flight-ops systems, flight plans, and operator dashboards |
| 071 | [Live comms, Remote ID, traffic](./071-live-comms-remote-id-and-traffic-integrations.md) | UTM/U-space, Remote ID broadcast, and traffic awareness |

---

## Calibration & validation track

A separate track for post-flight model calibration from real flight logs.
Tickets 080, 081, 082, and 083 are complete; only 084 (holdout validation
reports) remains.

| # | Ticket | Status |
|---|---|---|
| 080 | [Flight log ingestion & trace normalisation](./080-flight-log-ingestion-and-trace-normalization.md) | implemented |
| 081 | [Flight phase segmentation](./081-flight-phase-segmentation.md) | implemented |
| 082 | [Predicted vs. observed validation metrics](./082-predicted-vs-observed-validation-metrics.md) | implemented |
| 083 | [Calibration profile data & fitting](./083-calibration-profile-data-and-fitting.md) | implemented |
| 084 | [Holdout validation reports](./084-holdout-validation-reports.md) | planned |
| 102 | [Binary flight-log ingestion (.bin, ULog)](./102-binary-flight-log-ingestion.md) | planned |

---

## Contributing

**Before opening a PR, read the ticket file for the work you're doing.**
Each ticket states its acceptance criteria, composition with existing code, and
what tests are expected.

### Rules

- Keep core execution **deterministic**. Randomness lives in Monte Carlo and stochastic layers only.
- Add adapter layers only after core contracts are stable.
- **All schemas and public outputs are versioned.** Bump the version string when the shape changes.
- Reject unsupported inputs explicitly — never approximate silently.
- No live external network calls in core CI.
- **Update docs, tests, and golden fixtures in the same commit** when public behaviour changes.

### Integration standard

Every new ticket must compose through the existing surfaces:

- YAML schemas: `mission.v6`, `vehicle.v4`, `scenario.v1`, `uncertainty.v1`, `stochastic.v1`, `batch.v1`
- Examples: `examples/missions/`, `examples/vehicles/`, `examples/scenarios/`
- CLI commands: `estimate`, `scenario`, `sample`, `propagate`, `batch`, `convert`, `export`, `sitl`, `compare`, `size-battery`, `sora`
- Output contracts: canonical JSON envelopes, Markdown reports, golden fixtures
- Public Python API: `estimator.try_estimate_mission_distance_time`, `estimator.run_scenario`, `estimator.execution.monte_carlo.run_monte_carlo`

New capabilities should work *with* existing pieces, not alongside them in isolation.

---

## Implemented tickets

### Full list (78 tickets)

1. [001](./001-estimator-cli-and-envelope.md) Estimator CLI and envelope
2. [002](./002-versioning-and-golden-fixtures.md) Versioning and golden fixtures
3. [003](./003-technical-debt-hardening.md) Technical debt hardening
4. [010](./010-deterministic-energy-feasibility.md) Deterministic energy feasibility
5. [011](./011-static-geofence-feasibility.md) Static geofence feasibility
6. [012](./012-static-landing-zone-reachability.md) Static landing-zone reachability
7. [020](./020-scenario-runner-core.md) Scenario runner core
8. [021](./021-comms-link-and-contingency-policies.md) Comms link and contingency policies
9. [030](./030-fidelity-v2-layered-wind-and-subsegments.md) Fidelity v2 — layered wind and sub-segments
10. [031](./031-fidelity-v2-turns-and-fixed-wing-loiter.md) Fidelity v2 — turns and fixed-wing loiter
11. [032](./032-terrain-referenced-altitude-execution.md) Terrain-referenced altitude execution
12. [033](./033-continuous-spatiotemporal-wind-grid.md) Continuous spatiotemporal wind grid
13. [034](./034-resource-and-link-feasibility-abstractions.md) Resource and link feasibility abstractions
14. [035](./035-dynamic-landing-zone-availability.md) Dynamic landing-zone availability
15. [036](./036-computed-divert-routing.md) Computed divert routing
16. [037](./037-monte-carlo-uncertainty-modeling.md) Monte Carlo uncertainty modelling
17. [038](./038-bank-angle-and-dubins-path-optimization.md) Bank-angle and Dubins path optimisation
18. [039](./039-path-planning-model-gaps.md) Path planning model gaps
19. [040](./040-sitl-adapter-contract-and-evidence-schema.md) SITL adapter contract and evidence schema
20. [041](./041-ardupilot-sitl-launch-and-mission-upload.md) ArduPilot SITL launch and mission upload
21. [042](./042-sitl-telemetry-recorder-and-evidence-bundle.md) SITL telemetry recorder and evidence bundle
22. [043](./043-sitl-scenario-comparison-report.md) SITL scenario comparison report
23. [047](./047-stochastic-state-propagation.md) Stochastic state propagation
24. [048](./048-observation-model-and-twin-state.md) Observation model and twin-state EKF
25. [049](./049-stochastic-closed-loop-control.md) Stochastic closed-loop control
26. [052](./052-real-world-data-fetch-scripts.md) Real-world data fetch scripts
27. [053](./053-airspace-geofence-fetch-script.md) Airspace geofence fetch script
28. [055](./055-geojson-kml-route-export.md) GeoJSON and KML route export
29. [056](./056-community-vehicle-profiles.md) Community vehicle profiles
30. [057](./057-summary-output-format.md) Summary output format
31. [059](./059-infeasible-demo-mission.md) Infeasible demo mission
32. [060](./060-import-export-and-batch-workflows.md) Import, export, and batch workflows
33. [062](./062-wind-corrected-divert-energy.md) Wind-corrected divert energy *(LZ reachability TAS-only remaining — Ticket 062)*
34. [063](./063-rth-reserve-check.md) Return-to-home reserve check
35. [065](./065-geofence-and-lz-in-stochastic.md) Geofence and LZ in stochastic propagation
36. [069](./069-per-event-lost-link-policy-override.md) Per-event lost-link policy override
37. [072](./072-route-altitude-profile-report.md) Route altitude profile report
38. [073](./073-preflight-checklist-output.md) Pre-flight checklist output
39. [074](./074-energy-reserve-sensitivity.md) Energy reserve sensitivity report
40. [075](./075-minimum-battery-sizing.md) Minimum battery sizing command
41. [085](./085-qgc-convert-vehicle-profile.md) QGC convert vehicle profile selection
42. [086](./086-stochastic-propagator-module-split.md) Stochastic propagator module split
43. [094](./094-sora-ground-risk-class.md) SORA Ground Risk Class (iGRC)
44. [095](./095-sora-air-risk-and-sail.md) SORA Air Risk Class and SAIL determination
45. [091](./091-qgc-mission-export.md) QGC mission export
46. [092](./092-weather-minimums-and-go-nogo.md) Weather minimums and automatic GO/NO-GO
47. [093](./093-time-varying-geofence-activation.md) Time-varying geofence activation
48. [096](./096-docs-github-pages.md) Documentation site on GitHub Pages
49. [099](./099-energy-model-fidelity.md) Energy-model fidelity
50. [100](./100-obstacle-database-and-clearance.md) Obstacle database and vertical clearance checks
51. [101](./101-sora-mitigation-depth.md) SORA mitigation depth — M1–M3 and tactical air-risk reduction
52. [097](./097-rth-reserve-feasibility-gate.md) Opt-in RTH reserve feasibility gate
53. [061](./061-3d-geofence-altitude-bounds.md) 3D geofence altitude bounds
54. [080](./080-flight-log-ingestion-and-trace-normalization.md) Flight log ingestion and trace normalization
55. [081](./081-flight-phase-segmentation.md) Flight phase segmentation
56. [082](./082-predicted-vs-observed-validation-metrics.md) Predicted vs. observed validation metrics
57. [098](./098-version-bump-and-release-tooling.md) Version bump and release tooling
58. [083](./083-calibration-profile-data-and-fitting.md) Calibration profile data and fitting
59. [104](./104-atomic-output-writes-and-cancellation.md) Atomic output writes and clean cancellation
