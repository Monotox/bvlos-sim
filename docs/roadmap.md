# Roadmap

Where the project stands and what comes next. The authoritative work log is
the [ticket backlog](tickets/README.md); this page is the summary.

## Where it stands

The deterministic core is complete and contract-stable: estimation with two
fidelity modes, phase-based energy with RTH reserve gating, wind
(constant/layered/spatiotemporal grid), terrain, geofence, landing-zone,
obstacle, weather, resource, and link checks, the scenario runner with
lost-link/wind-change/landing-zone events, Monte Carlo sampling and
stochastic propagation diagnostics, SORA 2.5 pre-assessment, battery sizing,
QGC import/export, batch manifests, flight-log ingestion with
validation/calibration, and a live ArduPilot SITL evidence pipeline. All of
it is covered by golden-fixture and behavior tests (1600+ tests).

## Known gaps

- **No live data.** NOTAM/airspace feeds, live weather, UTM/U-space, Remote
  ID, and traffic integrations do not exist; every input is a static file
  (tickets 058, 070, 071).
- **ArduPilot-first ecosystem.** No PX4 SITL adapter (tickets 045, 046), no
  DJI wayline (WPML/KMZ) mission export, and flight-log ingestion reads
  ArduPilot DataFlash and PX4 ULog only — DJI/Autel/proprietary logs cannot
  close the calibration loop. The 64 MiB ingestion ceiling also excludes
  very long onboard logs; split them first.
- **Route expressiveness is minimal.** Six route actions; no per-leg speed
  changes, camera/payload actions, DO_ commands, jumps, or explicit VTOL
  transition points. Survey missions must be expressed as waypoint lists.
- **Single aircraft only.** No fleet or multi-aircraft concept; batch runs
  are fully independent estimates.
- **EASA SORA 2.5 only.** No SORA 2.0 or PDRA mode, and nothing directly
  submittable for FAA, UK, or Transport Canada processes. Segregated or
  atypical airspace (`atypical_or_segregated: true`) stays unsupported until
  an authority-evidence workflow exists.
- **SORA mitigation credit is fail-closed.** Applied M1/M2 declarations earn
  no credit until an Annex B criteria evaluator exists — the assessment is
  still reported, with each declaration marked
  `credit_rejected_pending_annex_b`; Annex E compliance is always
  `not_assessed`.
- **The readiness gate is a fixed check set.** Ops-manual categories outside
  the model (crew currency, NOTAM briefing, maintenance state) have no
  extension point yet; track them in your ops process, not in the tool.
- **Terrain is SRTM-only** — no coverage above ~60°N / below ~56°S.
- **No REST API or web UI** — CLI and Python only (ticket 050).
- **Not yet on PyPI.** The release workflow publishes from a version tag via
  Trusted Publishing, but until the first tagged release lands, installation is
  a git clone.
- **No bundled qualification corpus.** Ingestion, validation, and calibration
  are implemented, but each team must supply and govern its own
  representative flight logs and acceptance evidence. Until a vehicle declares
  `calibration_status: manufacturer_derived` or carries a fitted calibration
  profile, `ENERGY_MODEL_UNCALIBRATED` blocks the operational `GO`.
- **Gust, visibility, and precipitation limits fail closed** — no built-in
  provider supplies those observations yet.

## Direction

Priorities, in rough order:

1. Real-world accuracy: held-out validation on the calibration track, energy
   coefficient fitting.
2. PX4 SITL behind the existing adapter contract; DJI wayline export and
   log ingestion behind the existing conversion and trace contracts.
3. Route-action expressiveness (speed, payload, transitions) with QGC
   round-trip fidelity.
4. Live-data integrations (NOTAM/airspace first) as adapter-layer inputs.
5. Additional regulatory profiles (SORA 2.0/PDRA, FAA waiver support) and a
   declarable extension point for ops-manual readiness categories.
6. API/UI surfaces on top of the stable envelopes.

The constants that will not change: versioned contracts, deterministic
output, explicit unsupported outcomes, and a fail-closed verdict. New
capabilities land as adapters around that core, not as exceptions to it.
