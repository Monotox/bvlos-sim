# Ticket 087: Hardware-in-the-Loop (HITL) Adapter

## Status

Planned.

## Goal

Extend the SITL adapter contract to support hardware-in-the-loop (HITL)
validation, where the mission runs on real autopilot hardware (flight
controller + sensors) connected to a simulated environment, rather than on a
purely software-simulated autopilot. This is the final validation stage before
live flight and closes the gap between deterministic simulation and certified
airworthiness evidence.

## Why HIL Is the Logical Next Step

The current validation ladder is:

```
Deterministic estimate  →  Scenario runner  →  SITL (ArduPilot/PX4)  →  ???  →  Live flight
```

SITL validates mission logic and autopilot software in a controlled environment,
but it does not exercise the real hardware stack: the flight controller firmware,
sensor drivers, actuator interfaces, power rail behaviour, and real-time
scheduling. HITL fills this gap by:

1. Running the actual flight controller firmware on real hardware (e.g. a
   Pixhawk, Cube Orange, or CUAV X7) connected via USB or UART.
2. Feeding simulated GPS, IMU, barometer, and airspeed data to the hardware
   from a simulation model (Gazebo, JSBSim, ArduPilot SITL in HIL mode, or
   similar).
3. Capturing the hardware's actual MAVLink output (attitude, position,
   mission progress, failsafe events) as evidence artifacts.
4. Comparing observed HIL telemetry against the deterministic scenario
   expectations using the same `sitl-comparison.v1` report already defined by
   Ticket 043.

This means the same `bvlos-sim sitl` + `bvlos-sim compare` workflow used for
SITL can be reused for HITL with minimal adapter changes — the only difference
is the connection target (real hardware instead of a software process) and an
additional hardware descriptor in the evidence bundle.

## Ultimate Validation State

The full validation ladder bvlos-sim is designed for:

| Stage | Inputs | What Is Exercised |
|-------|--------|-------------------|
| Deterministic estimate | Mission YAML + vehicle profile | Route feasibility, energy, geofence, landing zone |
| Scenario runner | Mission + scenario YAML | Lost-link policies, events, contingency logic |
| Monte Carlo / stochastic | Uncertainty plan | Statistical feasibility under parameter variation |
| SITL (Tickets 041–043, 045–046) | ArduPilot / PX4 process | Autopilot software, MAVLink protocol, mission execution |
| **HITL (this ticket)** | Real flight controller hardware | Firmware + sensor drivers + actuator interfaces + real-time OS |
| Pre-flight ground check | Real aircraft, engines off | Sensor calibration, compass, battery state, arming |
| Live flight | Airspace approval, operator | Full system under real atmospheric conditions |

The deterministic simulation, SITL, and HITL layers together produce the
evidence bundle trail required by emerging BVLOS certification frameworks
(EASA SORA, FAA BEYOND, UK CAA EVLOS/BVLOS frameworks).

## Current Gap

After Tickets 040–043 (ArduPilot SITL) and Tickets 045–046 (PX4 SITL) are
implemented, HITL remains unaddressed:

- No `hitl` adapter kind in the evidence schema.
- No hardware descriptor (board type, firmware version, hardware serial) in
  `SitlSimulatorMetadata`.
- No HIL-specific connection lifecycle (serial port, USB, companion computer
  bridge).
- No documentation on how to wire a Pixhawk to a simulation environment for
  HIL testing with this tool.

## Scope

### Schema changes

- Add `adapter_kind: hitl_ardupilot | hitl_px4` variants to the `SitlAdapter`
  kind enum used in `sitl-evidence.v1`.
- Extend `SitlSimulatorMetadata` with optional `hardware_descriptor`:
  ```yaml
  hardware_descriptor:
    board_id: "CubeOrange"
    firmware_version: "ArduPlane 4.5.3"
    hw_serial: "optional-serial"
    connection: "serial:///dev/ttyUSB0:57600"
  ```

### Adapter implementation

- Add `HitlArduPilotAdapter` (and later `HitlPx4Adapter`) behind the same
  `SitlAdapter` contract defined in Ticket 040.
- Connection lifecycle: open serial/USB port → wait for HEARTBEAT → upload
  mission → arm → start AUTO → poll MISSION_CURRENT → wait completion.
- For HIL the simulation environment (Gazebo, JSBSim) is assumed to already be
  running and feeding sensor data to the hardware; the adapter does not start
  or manage the simulation model.
- Record the same artifact types as SITL: telemetry log, command log, adapter
  lifecycle log.

### CLI

- Expose HIL via the existing `bvlos-sim sitl` command with a new
  `--hitl` flag (or `--adapter-kind hitl_ardupilot`):
  ```bash
  bvlos-sim sitl scenario.yaml \
    --hitl \
    --host /dev/ttyUSB0 --baud 57600 \
    --artifact-dir ./hitl_evidence/
  ```
- `bvlos-sim compare` works unchanged — the comparison report is
  `sitl-comparison.v1` regardless of whether the evidence came from SITL or
  HITL.

### Documentation

- Add `docs/hitl_setup.md` describing how to configure ArduPilot HITL mode
  with a Pixhawk + Gazebo or JSBSim.
- Add an example scenario in `examples/scenarios/` annotated for HITL use.

## Composition

- Requires Tickets 040–043 (ArduPilot SITL contract and evidence) as a
  prerequisite.
- Tickets 045–046 (PX4 SITL) should be implemented before the `HitlPx4Adapter`
  variant, but the ArduPilot HIL adapter can proceed independently.
- Comparison reporting (Ticket 043) and the `bvlos-sim compare` CLI are reused
  without changes.
- The stochastic propagation and Monte Carlo layers (Tickets 047–049) are
  orthogonal to HIL; operators may run both paths in parallel.

## Acceptance Criteria

- `bvlos-sim sitl scenario.yaml --hitl --host /dev/ttyUSB0 --baud 57600 --artifact-dir ./out/`
  produces a valid `sitl-evidence.v1` bundle with `adapter_kind: hitl_ardupilot`
  and a populated `hardware_descriptor` when a Pixhawk running ArduPlane in HIL
  mode is connected and the mission completes.
- `bvlos-sim compare out/evidence.json` produces a `sitl-comparison.v1` report
  comparing observed HIL telemetry against deterministic scenario expectations,
  identical in structure to a SITL comparison report.
- Contract-only mode (`bvlos-sim sitl scenario.yaml` without `--hitl`) is
  unaffected.
- All existing SITL and comparison tests continue to pass.
- `pymavlink` remains an optional dependency; the HIL adapter is guarded by the
  same `sitl` extras group.
