# Ticket 054: Reference Inputs for Calibration and Import Design

## Goal

Collect and commit concrete real-world reference inputs — PX4 flight logs and
QGC `.plan` mission files — so that the calibration pipeline (Tickets 080–082)
and the import/export workflows (Ticket 060) are designed against actual data
rather than invented structure. This ticket produces no new code; it produces
committed reference assets and a short design-note document for each.

## Background

Two upcoming work tracks need representative real-world inputs before
implementation begins:

1. **Calibration pipeline (Tickets 080–082)**: needs real drone flight logs to
   validate the energy and wind model against observed data. Designing the
   ingestion format without a concrete log in hand risks building to a schema
   that doesn't match what real autopilots emit.

2. **QGC importer (Ticket 060)**: needs a real `.plan` file to define the
   import schema against. The QGC JSON format has optional and version-varying
   fields that only become visible in actual examples.

## Source 1: PX4 Flight Logs

**Where**: `https://logs.px4.io` — public, no registration, thousands of real
flights.

**What to download**: 2–3 VTOL fixed-wing or multirotor logs that include:
- `vehicle_global_position` (lat, lon, alt)
- `battery_status` (voltage, current, remaining)
- `airspeed` (indicated and true airspeed)
- `wind_estimate` (east, north components)

**Filter criteria**:
- Flight duration > 5 minutes (enough data for phase segmentation)
- At least one cruise phase identifiable from airspeed > 10 m/s
- Battery drain visible from `remaining` field going from ~1.0 to ~0.6+

**Deliverables**:
- `reference/flight_logs/px4_vtol_example_1.ulg` (committed as binary)
- `reference/flight_logs/px4_multirotor_example_1.ulg`
- `reference/flight_logs/README.md` — what each log represents, vehicle type,
  approximate duration, and which ULog fields are present

**Design note to write**:
- `reference/flight_logs/design_notes.md`: field mapping from ULog topics to
  the bvlos-sim energy model inputs (`cruise_power_w`, `hover_power_w`,
  `cruise_speed_mps`); which fields are directly observable vs. derived;
  known gaps (e.g. ULog does not emit instantaneous power, it must be computed
  from V × I).

## Source 2: QGC Mission Files

**Where**: GitHub — search `filename:*.plan` in repositories of ArduPilot
example missions, university UAV labs, and competition teams (e.g.
`site:github.com filename:*.plan drone mission`).

**What to collect**: 2–3 `.plan` files covering:
- A simple transit mission (takeoff → waypoints → RTL)
- A survey/grid mission with many closely spaced waypoints
- A mission with speed and altitude changes mid-flight

**Deliverables**:
- `reference/qgc_plans/simple_transit.plan`
- `reference/qgc_plans/survey_grid.plan`
- `reference/qgc_plans/altitude_changes.plan`
- `reference/qgc_plans/README.md` — source, vehicle type, and what each file
  exercises

**Design note to write**:
- `reference/qgc_plans/design_notes.md`: annotated walkthrough of the JSON
  structure (`mission.items`, `MAV_CMD` codes, `autoContinue`, `frame` field
  for altitude reference, speed commands); field mapping to bvlos-sim
  `MissionPlan` and `RoutePoint`; list of MAVLink commands that have no
  bvlos-sim equivalent (survey patterns, camera triggers, ROI) and how the
  importer should handle them (skip, warn, or error).

## File Plan

New directory: `reference/`

| File | Purpose |
|---|---|
| `reference/flight_logs/px4_vtol_example_1.ulg` | Real VTOL flight log |
| `reference/flight_logs/px4_multirotor_example_1.ulg` | Real multirotor flight log |
| `reference/flight_logs/README.md` | Log provenance and field inventory |
| `reference/flight_logs/design_notes.md` | ULog → bvlos-sim field mapping |
| `reference/qgc_plans/simple_transit.plan` | QGC transit mission |
| `reference/qgc_plans/survey_grid.plan` | QGC survey mission |
| `reference/qgc_plans/altitude_changes.plan` | QGC mission with altitude variation |
| `reference/qgc_plans/README.md` | Plan provenance and structure summary |
| `reference/qgc_plans/design_notes.md` | QGC JSON → MissionPlan field mapping |

Modified files:

- `.gitattributes` — mark `*.ulg` and `*.plan` as binary to avoid line-ending
  mangling
- `docs/ROADMAP.md` — update Ticket 060 and Tickets 080–082 notes to reference
  `reference/` directory

## Acceptance Criteria

1. `reference/flight_logs/` contains at least 2 `.ulg` files readable with
   `pyulog` (`ulog_info reference/flight_logs/px4_vtol_example_1.ulg` exits 0).
2. `reference/flight_logs/design_notes.md` maps each ULog topic field to its
   bvlos-sim equivalent or explicitly notes it as unrepresented.
3. `reference/qgc_plans/` contains at least 2 `.plan` files parseable as JSON
   with a top-level `mission.items` array.
4. `reference/qgc_plans/design_notes.md` lists every `MAV_CMD` present in the
   collected files and its intended handling in the Ticket 060 importer.
5. No existing tests are affected (reference files are not imported by any
   estimator or test code).
6. `uv run ruff check` passes (no Python files added by this ticket).

## Relationship to Other Tickets

- **Ticket 060** (import/export): the QGC design notes from this ticket become
  the input schema specification for the importer. Ticket 060 should be started
  only after this ticket's design notes are written.
- **Ticket 080** (flight log ingestion): the ULog field mapping from this
  ticket becomes the first draft of the ingestion schema. The `.ulg` files
  become the first test fixtures.

## Out of Scope

- ArduPilot `.bin` log format — deferred; PX4 ULog is the MVP target.
- Parsing or validating any of these files at runtime — this ticket is
  reference assets and design notes only, no production code.
- YAML fixture generation from the logs — that belongs to Ticket 080.
