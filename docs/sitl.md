# SITL

Run missions against a real ArduPilot autopilot in software-in-the-loop, and
turn the runs into versioned evidence bundles. Live SITL is optional: the
default test suite and every other command work without it.

**Prerequisites:** Podman or Docker. Nothing else on the host — ArduPilot,
MAVLink, and the compilers live in the container (Ubuntu 22.04, ArduPilot
pinned to commit `6e37731eef65`).

## Run the container

```bash
# build (compiles ArduCopter and ArduPlane; takes a while the first time)
podman build -t bvlos-sitl sitl/

# keep it alive with the primary MAVLink ports published
podman run --rm -d --name bvlos-sitl -p 5760:5760 -p 5770:5770 \
  bvlos-sitl sleep infinity

# launch a vehicle inside it (foreground; Ctrl-C to stop)
podman exec -it bvlos-sitl /opt/ardupilot/sitl/launch.sh copter   # port 5760
podman exec -it bvlos-sitl /opt/ardupilot/sitl/launch.sh plane    # quadplane, port 5770
```

Both vehicles start at `52.0, 4.0, 12 m AMSL` — matching the bundled pipeline
mission — and run at 5× simulation speed. Verify connectivity:

```bash
podman exec bvlos-sitl nc -z 127.0.0.1 5760
```

Ports: `5760`/`5770` primary MAVLink (copter/plane), `5762-5763`/`5772-5773`
serial, `5501`/`5511` UDP sim sockets. Docker users: substitute `docker` for
`podman` throughout.

## Record evidence

The `sitl` command reuses an existing `scenario.v1` file — there is no
parallel SITL input format. Without `--live` it emits a *contract-only*
`sitl-evidence.v1` bundle: input references plus the embedded deterministic
scenario report, with empty telemetry artifact lists.

```bash
uv sync --extra sitl    # installs pymavlink

uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --live --host 127.0.0.1 --port 5770 \
  --artifact-dir /tmp/bvlos-artifacts \
  --telemetry-samples 20 \
  --output /tmp/sitl-evidence.json
```

A live run connects, uploads the mission, arms, flies AUTO, and records
telemetry. It reports `status: completed` only on explicit
mission-completion evidence — the final item merely becoming current is not
enough. The artifact directory receives `telemetry.json`, `command_log.json`,
`simulator_log.json`, and `adapter_log.json`; each is referenced from the
bundle with role, format, and SHA-256 checksum. Artifacts are caller-managed —
keep them with their inputs when preserving validation evidence.

The bundled pipeline scenario uses a QuadPlane profile — target the plane
launcher on port `5770`. Use `5760` only with an ArduCopter-compatible
mission.

Exit codes: invalid scenario/mission/vehicle/asset input is `11`; live
connect, upload, execution, telemetry, completion, and timeout failures are
`13` (runtime, not operator error). Failed runs still flush recorded
artifacts for diagnosis.

## Compare against expectations

```bash
uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --output /tmp/sitl-comparison.json      # --format markdown also supported
```

`compare` renders a `sitl-comparison.v1` report over a completed bundle:
scenario assertions, mission item count, telemetry presence, adapter and
simulator lifecycle, and position proximity (default tolerance 500 m) when
`GLOBAL_POSITION_INT` telemetry exists. Exit `0` = `passed`, `10` =
`drifted`/`failed` (review the changed dimensions), `12` = the bundle is
contract-only and there is nothing live to compare.

The same builders are available as Python APIs
(`adapters.sitl.comparison.build_sitl_comparison_report` and the JSON/Markdown
renderers).

## Adapter boundary

SITL adapters live outside the deterministic core, and the boundary is
enforced:

- Simulator/MAVLink dependencies are allowed only in `adapters/` modules, CLI
  entry points that call them, and optional integration environments.
- `estimator/core`, `estimator/execution`, and `schemas` never import
  simulator or MAVLink packages, and no estimator, scenario, or uncertainty
  output ever depends on a live simulator.
- The default test suite runs without ArduPilot; live tests
  (`pytest -m live_sitl`) need the container and `uv sync --extra sitl`.
- SITL output is conformance evidence against the deterministic expectations —
  never real-world calibration and never operational approval.

A PX4 adapter behind the same contract is planned
([roadmap](roadmap.md)).
