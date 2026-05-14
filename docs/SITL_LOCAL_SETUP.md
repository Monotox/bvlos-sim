# Local SITL Setup

This guide describes the local ArduPilot SITL container used for bvlos-sim
development. It is only about rebuilding and running the verified local
environment. For the adapter boundary and evidence contract, see
[SITL_ADAPTER_CONTRACT.md](./SITL_ADAPTER_CONTRACT.md).

## Prerequisites

- Podman or Docker.
- No ArduPilot, MAVLink, Python, or compiler tooling is required on the host
  when using the container workflow.

The container is based on `docker.io/library/ubuntu:22.04` and pins ArduPilot to
commit `6e37731eef65b485994ae5109f03c518bc73853f`.

## Build the container

From the repository root:

```bash
podman build -t bvlos-sitl sitl/
```

Docker users can run the equivalent:

```bash
docker build -t bvlos-sitl sitl/
```

## Run the container

For the `podman exec` workflow, keep the container alive and publish the primary
MAVLink TCP ports:

```bash
podman run --rm -d --name bvlos-sitl \
  -p 5760:5760 \
  -p 5770:5770 \
  bvlos-sitl sleep infinity
```

Optional extra socket ports:

```bash
podman run --rm -d --name bvlos-sitl \
  -p 5760:5760 \
  -p 5762:5762 \
  -p 5763:5763 \
  -p 5770:5770 \
  -p 5772:5772 \
  -p 5773:5773 \
  -p 5501:5501/udp \
  -p 5511:5511/udp \
  bvlos-sitl sleep infinity
```

## Launch SITL inside the container

Launch ArduCopter:

```bash
podman exec -it bvlos-sitl /opt/ardupilot/sitl/launch.sh copter
```

Launch ArduPlane in the verified quadplane frame:

```bash
podman exec -it bvlos-sitl /opt/ardupilot/sitl/launch.sh plane
```

The launcher runs SITL in the foreground. Stop it with `Ctrl-C`, or stop the
container:

```bash
podman stop bvlos-sitl
```

## Verify MAVLink connectivity

After launching ArduCopter, verify the primary TCP MAVLink endpoint:

```bash
podman exec bvlos-sitl nc -z 127.0.0.1 5760
```

Then verify a heartbeat with `pymavlink` inside the container:

```bash
podman exec bvlos-sitl python3 -c "
from pymavlink import mavutil
m = mavutil.mavlink_connection('tcp:127.0.0.1:5760')
hb = m.wait_heartbeat(timeout=20)
print('Connected - system', m.target_system)
m.close()
"
```

For ArduPlane, use port `5770` in the same checks.

## Ports reference

| Port | Protocol | Role |
| --- | --- | --- |
| 5760 | TCP | ArduCopter primary MAVLink |
| 5762 | TCP | ArduCopter serial 0 |
| 5763 | TCP | ArduCopter serial 1 |
| 5501 | UDP | ArduCopter SITL sim socket |
| 5770 | TCP | ArduPlane primary MAVLink |
| 5772 | TCP | ArduPlane serial 0 |
| 5773 | TCP | ArduPlane serial 1 |
| 5511 | UDP | ArduPlane SITL sim socket |

## Known limitations

- The Ubuntu 22.04 apt repositories do not provide `mavproxy`, so the
  Containerfile installs `MAVProxy==1.8.74` with `pip3`.
- ArduPilot's `install-prereqs-ubuntu.sh` refuses to run as root. The
  Containerfile installs the required package set directly instead of calling
  that script.
- The apt `python3-ply` package produced a corrupted `yacc.py` in the verified
  manual setup. The Containerfile avoids apt `python3-ply`.
- Optional apt packages around `python3-pythran`, `scipy`, and `matplotlib`
  failed to configure in the verified manual setup. The Containerfile skips
  them because the live MAVLink smoke path does not require them.
- Do not pass `--out=tcpin:0.0.0.0:576x` to `sim_vehicle.py` for this setup.
  ArduPilot already binds the standard TCP ports internally. The launcher uses
  `--no-mavproxy`.

## Artifact layout and retention

Live SITL adapter runs can write a self-contained artifact directory for the
evidence bundle. The ArduPilot adapter writes deterministic JSON files named
`telemetry.json`, `command_log.json`, `simulator_log.json`, and
`adapter_log.json`. Each artifact reference in `sitl-evidence.v1` includes the
path, role, format, schema version, and SHA-256 checksum.

Artifact directories are caller-managed local files. Keep them with the
corresponding mission, vehicle, and scenario inputs when preserving validation
evidence, or remove them after short-lived smoke tests. The project does not
upload, rotate, or prune SITL artifacts automatically.

## Default CI behaviour

Live ArduPilot SITL is optional for bvlos-sim. Default development and CI tests
continue to run without ArduPilot or host MAVLink tooling, for example with
`uv run pytest`. The optional SITL dependency group,
`uv sync --group sitl`, is only needed for live adapter tests.
