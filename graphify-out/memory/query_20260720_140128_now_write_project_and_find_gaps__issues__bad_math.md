---
type: "query"
date: "2026-07-20T14:01:28.190682+00:00"
question: "now write project and find gaps, issues, bad math, bad science or anything that will prevent a real team from using it"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Obstacle Clearance Evaluation", "Population Ground-Risk Computation", "Geodesic Dubins Routing", "Energy and RTH Fidelity", "SORA Risk Assessment", "Monte Carlo Uncertainty", "SITL Artifact Recording", "Calibration Parameter Fitting", "Estimation Context and Environment"]
---

# Q: now write project and find gaps, issues, bad math, bad science or anything that will prevent a real team from using it

## Answer

Verdict: NO-GO for operational flight decision authority; usable as an alpha engineering/simulation sandbox. Expanded from the original query via graph vocabulary: [accuracy, battery, energy, error, failure, geodesic, model, risk, safety, stochastic, uncertainty, validation]. Graph traversal was followed by source inspection, targeted reproductions, official JARUS comparison, packaging checks, and the full automated suite.

Blocking findings:

1. Spatial clearance is fail-open. Obstacle, terrain, and population checks use sampled route points; a default leg has only its midpoint. A tall obstacle at one-quarter of a 176.8 m leg was missed. Missing terrain coverage is accepted as no violation, and missing population coverage is discarded and defaults to zero density/iGRC 2. Grid indexing also uses int() so points just south/west of the origin extrapolate the first cell.
2. Fidelity-v2 turn geometry is impossible. A nonzero R*angle turn arc is recorded with identical start/end coordinates and zero horizontal displacement. Geofence, obstacle, terrain, and population consumers therefore inspect the turn as a point. Tangent offsets are clamped without a path-fit check and times are not recomputed, so distance, time, energy, and geometry disagree.
3. SORA output conforms to neither labeled SORA 2.0 nor SORA 2.5. The engine labels results 2.0 but uses truncated 2.5-style density bands, ignores maximum speed and 20/40 m columns, fabricates unsupported cells, uses incorrect M1 credits/floors, and lowers ARC/SAIL using tactical mitigation in the wrong process step.
4. Any partial EstimationOptions object overrides all mission wind with default zeroes and ignores mission wind layers. Reproduction: adding only fidelity=v2 changed a -5 m/s mission wind to 0 and reduced time from 52.83 s to 38.15 s; CLI-only fidelity/segmentation overrides can turn a wind-infeasible mission feasible.
5. Wind constraints are checked only at the start of subsegmented legs. Later wind, crosswind, crab-angle, and minimum-groundspeed violations can pass and the reported worst values stay zero.
6. Energy math selects power from the command phase rather than actual vertical motion. A pure 220 m waypoint climb used 450 W cruise power and 9.17 Wh instead of configured 1,500 W climb power and 30.56 Wh. The universal rho_ref/rho multiplier is also not a valid common density law for hover and fixed-wing power.
7. The hard RTH reserve gate uses straight distance/TAS and ignores wind, turns, vertical/landing energy, terrain, obstacles, and geofences. A 15 m/s return headwind at 18 m/s TAS makes energy six times the calm estimate; headwind at or above TAS still produces finite feasible RTH energy.
8. Monte Carlo feasibility has survivorship bias: kinematically INFEASIBLE samples with no energy result disappear from the denominator. A reproduction with 71 impossible flights out of 100 reported 100% feasible. Other uncertainty defects include dead wind process-noise state, a shared reserve threshold across sampled battery capacities, one-component sampling zeroing the other deterministic wind component, and exclusive p5/p95 estimates outside the sample range for small N.
9. Live SITL evidence does not arm, start, or wait for mission completion. It uploads a mission and samples telemetry; any telemetry marks the bundle COMPLETED, so an aircraft that never flies may produce passed evidence. CI skips all nine live-SITL cases.
10. Environmental fetchers convert missing wind, terrain, and population values to plausible zeroes and omit adequate source/version/freshness/coverage metadata. This can make null weather calm, mountains sea level, and populated areas empty.
11. Calibration writes mean observed groundspeed into a parameter later treated as TAS and applies wind again, causing wind double-counting. Dataset versions hash trace IDs rather than content/segmentation, validation can reuse training data, and there is no held-out acceptance gate or real .bin/.ulg qualification corpus.
12. Production integration is unsafe around files and packaging: progress output can overwrite the input plan; NaN/Inf can be emitted as invalid JSON; requests is undeclared for fetch scripts; wheel extras/commands do not match advertised functionality; installed bump crashes outside a source checkout; batch profiles discard terrain evidence and can retain stale successful outputs.

Operational gaps: the checklist can say GO with RTH infeasible because the hard gate defaults off; weather evidence can be absent or unenforced; there are no live NOTAM/traffic/comms/Remote-ID integrations; validation has metrics but no pass/fail thresholds; release CI does not gate the wheel, live mission execution, or representative held-out flight data. The roadmap and package classifier correctly identify the project as alpha/planned operational integration.

Validation baseline: ruff clean; 1,272 tests passed and 9 live-SITL tests skipped; CLI batch audit 86/86 passed; wheel build/install smoke passed. These results establish internal regression quality but do not cover the reproduced safety failures. No estimator source was modified during the audit.

Recommended gate order: first disable or relabel operator-facing GO/SORA/RTH outputs; make missing data and partial overrides fail closed; replace turn/spatial geometry; fix wind/energy/RTH/SORA/Monte Carlo math; then add executed SITL, strict artifact/wheel CI, real-flight held-out validation, uncertainty/error budgets, and regulator-reviewed acceptance evidence.

## Outcome

- Signal: useful

## Source Nodes

- Obstacle Clearance Evaluation
- Population Ground-Risk Computation
- Geodesic Dubins Routing
- Energy and RTH Fidelity
- SORA Risk Assessment
- Monte Carlo Uncertainty
- SITL Artifact Recording
- Calibration Parameter Fitting
- Estimation Context and Environment