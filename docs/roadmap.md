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
- **No PX4 SITL adapter** — ArduPilot only (tickets 045, 046).
- **No REST API or web UI** — CLI and Python only (ticket 050).
- **No bundled qualification corpus.** Ingestion, validation, and calibration
  are implemented, but each team must supply and govern its own
  representative flight logs and acceptance evidence.
- **SORA mitigation credit is fail-closed.** Applied M1/M2 declarations are
  rejected until an Annex B criteria evaluator exists; Annex E compliance is
  always `not_assessed`.
- **Gust, visibility, and precipitation limits fail closed** — no built-in
  provider supplies those observations yet.

## Direction

Priorities, in rough order:

1. Real-world accuracy: held-out validation on the calibration track, energy
   coefficient fitting.
2. PX4 SITL behind the existing adapter contract.
3. Live-data integrations (NOTAM/airspace first) as adapter-layer inputs.
4. API/UI surfaces on top of the stable envelopes.

The constants that will not change: versioned contracts, deterministic
output, explicit unsupported outcomes, and a fail-closed verdict. New
capabilities land as adapters around that core, not as exceptions to it.
