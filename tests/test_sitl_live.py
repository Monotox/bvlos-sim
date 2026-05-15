"""Live ArduPilot SITL integration tests.

These tests are skipped unless a prepared ``bvlos-sitl`` podman container is
running and reachable from the host executing pytest.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from adapters.io import load_vehicle as _load_vehicle
from schemas import (
    AltitudeReference,
    MissionAction,
    MissionConstraints,
    MissionDefaults,
    MissionPlan,
    PlannedHome,
    RouteItem,
    VehicleProfile,
)

CONTAINER_NAME = "bvlos-sitl"
COPTER_PORT = 5760
PLANE_PORT = 5770
SITL_STARTUP_TIMEOUT_S = 30
TELEMETRY_SAMPLE_COUNT = 5

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VEHICLE_PATH = _REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
_PODMAN_ENV_VAR = "BVLOS_PODMAN"


def _podman_executable() -> str | None:
    return os.environ.get(_PODMAN_ENV_VAR) or shutil.which("podman")


def _podman_command(*args: str) -> list[str]:
    executable = _podman_executable()
    if executable is None:
        raise FileNotFoundError("podman")
    return [executable, *args]


def _podman_available() -> bool:
    return _podman_executable() is not None


def _container_running() -> bool:
    try:
        result = subprocess.run(
            _podman_command(
                "inspect",
                CONTAINER_NAME,
                "--format",
                "{{.State.Status}}",
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "running"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _container_ip() -> str | None:
    """Return the container's internal IP address for direct TCP access."""

    try:
        result = subprocess.run(
            _podman_command(
                "inspect",
                CONTAINER_NAME,
                "--format",
                "{{.NetworkSettings.IPAddress}}",
            ),
            capture_output=True,
            text=True,
            timeout=5,
        )
        ip = result.stdout.strip()
        return ip if ip else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _mapped_host_for_port(port: int) -> str | None:
    """Return a published host address for a container TCP port, if present."""

    try:
        result = subprocess.run(
            _podman_command("port", CONTAINER_NAME, f"{port}/tcp"),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None

    value = result.stdout.strip().splitlines()
    if not value:
        return None
    host = value[0].rsplit(":", maxsplit=1)[0]
    if host in {"0.0.0.0", "::", "[::]"}:
        return "127.0.0.1"
    return host.strip("[]")


def _sitl_binary_present(vehicle: str) -> bool:
    """Check if the ArduPilot binary exists inside the container."""

    binary_names = (
        ("ArduCopter", "arducopter")
        if vehicle == "copter"
        else ("ArduPlane", "arduplane")
    )
    for binary in binary_names:
        try:
            result = subprocess.run(
                _podman_command(
                    "exec",
                    CONTAINER_NAME,
                    "test",
                    "-f",
                    f"/opt/ardupilot/build/sitl/bin/{binary}",
                ),
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        if result.returncode == 0:
            return True
    return False


def _port_open_in_container(
    port: int,
    timeout_s: float = SITL_STARTUP_TIMEOUT_S,
) -> bool:
    """Poll until port is open inside the container or timeout."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                _podman_command(
                    "exec",
                    CONTAINER_NAME,
                    "nc",
                    "-z",
                    "127.0.0.1",
                    str(port),
                ),
                capture_output=True,
                timeout=3,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        if result.returncode == 0:
            return True
        time.sleep(1)
    return False


def _port_reachable_from_host(host: str, port: int, timeout_s: float = 3.0) -> bool:
    """Check if port is reachable from the host at the given IP."""

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _launch_sitl_background(vehicle: str) -> None:
    """Start ArduPilot SITL in background inside container. No-op if already up."""

    port = COPTER_PORT if vehicle == "copter" else PLANE_PORT
    if _port_open_in_container(port, timeout_s=1.0):
        return
    try:
        subprocess.Popen(
            _podman_command(
                "exec",
                CONTAINER_NAME,
                "/opt/ardupilot/sitl/launch.sh",
                vehicle,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return


def _host_for_port(port: int) -> str | None:
    return (
        os.environ.get("BVLOS_SITL_HOST")
        or _mapped_host_for_port(port)
        or _CONTAINER_IP
    )


def _require_host_port(port: int) -> str:
    host = _host_for_port(port)
    if host is None:
        pytest.skip(
            "live SITL adapter tests require a container IP or mapped host port"
        )
    if not _port_reachable_from_host(host, port):
        pytest.skip(f"live SITL port {port} is not reachable from host {host}")
    return host


def _vehicle() -> VehicleProfile:
    vehicle, _ = _load_vehicle(_VEHICLE_PATH)
    return vehicle


def _sitl_mission() -> MissionPlan:
    """Minimal three-waypoint mission compatible with ArduCopter SITL."""

    return MissionPlan(
        mission_id="sitl-live-test",
        vehicle_profile="quadplane_v1",
        planned_home=PlannedHome(lat=52.0, lon=4.0, altitude_amsl_m=10.0),
        defaults=MissionDefaults(
            altitude_reference=AltitudeReference.RELATIVE_HOME,
        ),
        route=[
            RouteItem(
                id="wp1",
                action=MissionAction.WAYPOINT,
                lat=52.001,
                lon=4.001,
                altitude_m=50.0,
            ),
            RouteItem(
                id="wp2",
                action=MissionAction.WAYPOINT,
                lat=52.002,
                lon=4.002,
                altitude_m=50.0,
            ),
            RouteItem(
                id="wp3",
                action=MissionAction.WAYPOINT,
                lat=52.001,
                lon=4.001,
                altitude_m=50.0,
            ),
        ],
        constraints=MissionConstraints(),
    )


_PODMAN_OK = _podman_available()
_CONTAINER_OK = _PODMAN_OK and _container_running()
_CONTAINER_IP = _container_ip() if _CONTAINER_OK else None

requires_live_sitl = pytest.mark.skipif(
    not _CONTAINER_OK,
    reason=(
        "live SITL tests require podman with bvlos-sitl container running "
        f"(podman={_PODMAN_OK}, container={_CONTAINER_OK}, ip={_CONTAINER_IP})"
    ),
)

requires_copter_binary = pytest.mark.skipif(
    not (_CONTAINER_OK and _sitl_binary_present("copter")),
    reason="ArduCopter SITL binary not found in container",
)

requires_plane_binary = pytest.mark.skipif(
    not (_CONTAINER_OK and _sitl_binary_present("plane")),
    reason="ArduPlane SITL binary not found in container",
)


def test_podman_command_uses_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_PODMAN_ENV_VAR, "custom-podman")

    assert _podman_command("inspect", CONTAINER_NAME) == [
        "custom-podman",
        "inspect",
        CONTAINER_NAME,
    ]


def test_host_for_port_uses_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BVLOS_SITL_HOST", "127.0.0.1")

    assert _host_for_port(COPTER_PORT) == "127.0.0.1"


@pytest.mark.live_sitl
@requires_live_sitl
def test_container_is_reachable_and_has_pymavlink() -> None:
    """The container is running and pymavlink is installed inside it."""

    result = subprocess.run(
        _podman_command(
            "exec",
            CONTAINER_NAME,
            "python3",
            "-c",
            "from pymavlink import mavutil; print('ok')",
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"pymavlink not available in container: {result.stderr}"
    )
    assert "ok" in result.stdout


@pytest.mark.live_sitl
@requires_live_sitl
@requires_copter_binary
def test_ardupilot_copter_sitl_launches_and_binds_port(tmp_path: Path) -> None:
    """ArduCopter SITL can be launched and reaches port 5760 inside the container."""

    del tmp_path
    _launch_sitl_background("copter")
    assert _port_open_in_container(COPTER_PORT), (
        f"ArduCopter SITL did not bind port {COPTER_PORT} within "
        f"{SITL_STARTUP_TIMEOUT_S}s"
    )


@pytest.mark.live_sitl
@requires_live_sitl
@requires_copter_binary
def test_adapter_connects_and_receives_heartbeat() -> None:
    """ArduPilotSitlAdapter connects to the container SITL and receives a heartbeat."""

    from adapters.ardupilot_sitl import ArduPilotSitlAdapter
    from adapters.ardupilot_sitl_types import ArduPilotSitlConfig

    _launch_sitl_background("copter")
    assert _port_open_in_container(COPTER_PORT), "SITL port not ready"
    host = _require_host_port(COPTER_PORT)

    config = ArduPilotSitlConfig(host=host, port=COPTER_PORT)
    adapter = ArduPilotSitlAdapter(config)
    try:
        adapter.connect()
        metadata = adapter.simulator_metadata(_vehicle())
        assert metadata.adapter_kind.value == "ardupilot"
        assert metadata.execution_mode == "live_sitl"
    finally:
        adapter.disconnect()


@pytest.mark.live_sitl
@requires_live_sitl
@requires_copter_binary
def test_adapter_uploads_mission_to_sitl(tmp_path: Path) -> None:
    """ArduPilotSitlAdapter uploads a mission to the live SITL without error."""

    from adapters.ardupilot_sitl import ArduPilotSitlAdapter
    from adapters.ardupilot_sitl_types import ArduPilotSitlConfig

    _launch_sitl_background("copter")
    assert _port_open_in_container(COPTER_PORT), "SITL port not ready"
    host = _require_host_port(COPTER_PORT)

    config = ArduPilotSitlConfig(host=host, port=COPTER_PORT)
    adapter = ArduPilotSitlAdapter(config)
    adapter.start_recording(tmp_path)
    try:
        adapter.connect()
        result = adapter.upload_mission(_sitl_mission())
        assert result.acknowledged is True
        assert result.item_count > 0
    finally:
        adapter.disconnect()

    observed = adapter.flush_artifacts()
    assert observed.command_logs, "command log must record mission upload commands"
    assert observed.adapter_logs, "adapter log must record adapter lifecycle events"
    command_log_path = Path(observed.command_logs[0].path)
    commands = json.loads(command_log_path.read_text(encoding="utf-8"))["commands"]
    command_names = [command["command"] for command in commands]
    assert "MISSION_COUNT" in command_names
    assert "MISSION_ITEM_INT" in command_names


@pytest.mark.live_sitl
@requires_live_sitl
@requires_copter_binary
def test_adapter_records_telemetry_from_live_sitl(tmp_path: Path) -> None:
    """Telemetry recording captures real MAVLink messages from ArduCopter SITL."""

    from adapters.ardupilot_sitl import ArduPilotSitlAdapter
    from adapters.ardupilot_sitl_mavlink import RUN_STATE_MESSAGE_TYPES
    from adapters.ardupilot_sitl_types import ArduPilotSitlConfig

    _launch_sitl_background("copter")
    assert _port_open_in_container(COPTER_PORT), "SITL port not ready"
    host = _require_host_port(COPTER_PORT)

    config = ArduPilotSitlConfig(host=host, port=COPTER_PORT)
    adapter = ArduPilotSitlAdapter(config)
    adapter.start_recording(tmp_path)
    try:
        adapter.connect()
        observed = adapter.record_telemetry(
            sample_count=TELEMETRY_SAMPLE_COUNT,
            timeout_s=10.0,
        )
    finally:
        adapter.disconnect()

    assert observed.telemetry, "telemetry artifact must be produced"
    telemetry_path = Path(observed.telemetry[0].path)
    assert telemetry_path.exists()
    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    assert telemetry["schema_version"] == "sitl-telemetry.v1"
    records = telemetry["records"]
    assert len(records) == TELEMETRY_SAMPLE_COUNT
    for record in records:
        assert "timestamp_s" in record
        assert "message_type" in record
        assert record["message_type"] in RUN_STATE_MESSAGE_TYPES
        assert "fields" in record


@pytest.mark.live_sitl
@requires_live_sitl
@requires_copter_binary
def test_full_evidence_bundle_has_completed_status(tmp_path: Path) -> None:
    """A full SITL run produces a COMPLETED evidence bundle."""

    from adapters.ardupilot_sitl import ArduPilotSitlAdapter
    from adapters.ardupilot_sitl_types import ArduPilotSitlConfig
    from adapters.io import load_mission, load_vehicle
    from adapters.scenario_envelope import build_scenario_envelope
    from adapters.scenario_io import load_scenario
    from adapters.sitl_evidence import build_sitl_evidence_bundle
    from estimator.execution.scenario import run_scenario
    from schemas import SitlEvidenceStatus

    _launch_sitl_background("copter")
    assert _port_open_in_container(COPTER_PORT), "SITL port not ready"
    host = _require_host_port(COPTER_PORT)

    scenario_path = (
        _REPO_ROOT / "examples" / "scenarios" / "pipeline_demo_001_scenario.yaml"
    )
    scenario_plan, scenario_doc = load_scenario(scenario_path)
    mission_path = scenario_path.parent / scenario_plan.mission_file
    vehicle_path = scenario_path.parent / scenario_plan.vehicle_file
    mission_model, mission_doc = load_mission(mission_path)
    vehicle_model, vehicle_doc = load_vehicle(vehicle_path)

    scenario_result = run_scenario(scenario_plan, mission_model, vehicle_model)
    scenario_env = build_scenario_envelope(
        result=scenario_result,
        scenario_document=scenario_doc,
        mission_document=mission_doc,
        vehicle_document=vehicle_doc,
    )

    config = ArduPilotSitlConfig(host=host, port=COPTER_PORT)
    adapter = ArduPilotSitlAdapter(config)
    adapter.start_recording(tmp_path)
    try:
        adapter.connect()
        adapter.upload_mission(mission_model)
        adapter.record_telemetry(
            sample_count=TELEMETRY_SAMPLE_COUNT,
            timeout_s=10.0,
        )
    finally:
        adapter.disconnect()

    bundle = build_sitl_evidence_bundle(
        evidence_id=f"{scenario_plan.scenario_id}-sitl-live",
        scenario_envelope=scenario_env,
        scenario_document=scenario_doc,
        mission_document=mission_doc,
        vehicle_document=vehicle_doc,
        vehicle=vehicle_model,
        adapter=adapter,
    )

    assert bundle.status == SitlEvidenceStatus.COMPLETED
    assert bundle.metadata["contract_only"] is False
    assert bundle.observed.telemetry, "completed bundle must have telemetry"
    assert bundle.observed.command_logs, "completed bundle must have command log"
    assert bundle.observed.adapter_logs, "completed bundle must have adapter log"
    assert bundle.simulator.execution_mode == "live_sitl"
    assert bundle.simulator.adapter_kind.value == "ardupilot"
    json.dumps(bundle.model_dump(mode="json"), sort_keys=True)
