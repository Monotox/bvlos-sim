"""Tests for the ArduPilot SITL adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adapters.sitl.ardupilot import (
    ArduPilotAdapterError,
    ArduPilotSitlAdapter,
    MissionUploadResult,
    altitude_reference_to_mavlink_frame,
    mission_action_to_mavlink_cmd,
)
from adapters.sitl.ardupilot_types import ArduPilotSitlConfig
from adapters.io import InputDocument, load_vehicle
from adapters.scenario_envelope import ScenarioResultEnvelope, build_scenario_envelope
from adapters.sitl.evidence import build_sitl_evidence_bundle
from estimator.core.scenario import ScenarioResult, ScenarioStatus
from schemas import (
    AltitudeReference,
    MissionAction,
    MissionConstraints,
    MissionDefaults,
    MissionPlan,
    PlannedHome,
    RouteItem,
    SitlAdapterKind,
    SitlEvidenceStatus,
    VehicleProfile,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
VEHICLE_PATH = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"


class FakeMavlink:
    MAV_CMD_COMPONENT_ARM_DISARM = 400
    MAV_MISSION_ACCEPTED = 0
    MAV_MISSION_TYPE_MISSION = 0
    MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1


class FakeMessage:
    def __init__(self, message_type: str, **fields: object) -> None:
        self.message_type = message_type
        for name, value in fields.items():
            setattr(self, name, value)

    def get_type(self) -> str:
        return self.message_type


class FakeMav:
    def __init__(self) -> None:
        self.mission_counts: list[tuple[object, ...]] = []
        self.mission_items: list[tuple[object, ...]] = []
        self.command_longs: list[tuple[object, ...]] = []
        self.set_modes: list[tuple[object, ...]] = []

    def mission_count_send(self, *args: object) -> None:
        self.mission_counts.append(args)

    def mission_item_int_send(self, *args: object) -> None:
        self.mission_items.append(args)

    def command_long_send(self, *args: object) -> None:
        self.command_longs.append(args)

    def set_mode_send(self, *args: object) -> None:
        self.set_modes.append(args)


class FakeConnection:
    def __init__(self, messages: list[FakeMessage] | None = None) -> None:
        self.mav = FakeMav()
        self.target_system = 1
        self.target_component = 1
        self.messages = messages or []
        self.closed = False
        self.heartbeat_requested = False
        self.heartbeat_timeout: float | None = None
        self.connection_string: str | None = None
        self.mode: str | None = None

    def wait_heartbeat(self, timeout: float) -> FakeMessage:
        self.heartbeat_requested = True
        self.heartbeat_timeout = timeout
        return FakeMessage("HEARTBEAT")

    def recv_match(
        self,
        *,
        type: list[str],
        blocking: bool,
        timeout: float,
    ) -> FakeMessage | None:
        del type, blocking, timeout
        if not self.messages:
            return None
        return self.messages.pop(0)

    def close(self) -> None:
        self.closed = True
        self.target_system = 0
        self.target_component = 0

    def set_mode(self, mode: str) -> None:
        self.mode = mode


class FakeMavutil:
    mavlink = FakeMavlink

    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.connection_args: tuple[object, ...] | None = None
        self.connection_kwargs: dict[str, object] | None = None

    def mavlink_connection(self, *args: object, **kwargs: object) -> FakeConnection:
        self.connection_args = args
        self.connection_kwargs = kwargs
        self.connection.connection_string = str(args[0])
        return self.connection


class MissingHeartbeatConnection(FakeConnection):
    def wait_heartbeat(self, timeout: float) -> None:
        self.heartbeat_requested = True
        self.heartbeat_timeout = timeout
        return None


class StubbedArduPilotSitlAdapter(ArduPilotSitlAdapter):
    def __init__(self, connection: FakeConnection) -> None:
        super().__init__()
        self.fake_mavutil = FakeMavutil(connection)

    def _mavutil(self) -> FakeMavutil:
        return self.fake_mavutil


def _mission(route: list[RouteItem]) -> MissionPlan:
    return MissionPlan(
        mission_id="test-mission",
        vehicle_profile="quadplane_v1",
        planned_home=PlannedHome(
            lat=52.0,
            lon=4.0,
            altitude_amsl_m=10.0,
        ),
        defaults=MissionDefaults(
            altitude_reference=AltitudeReference.RELATIVE_HOME,
        ),
        route=route,
        constraints=MissionConstraints(),
    )


def _waypoint(item_id: str, offset: float = 0.0) -> RouteItem:
    return RouteItem(
        id=item_id,
        action=MissionAction.WAYPOINT,
        lat=52.0 + offset,
        lon=4.0 + offset,
        altitude_m=100.0,
    )


def _three_item_mission() -> MissionPlan:
    return _mission(
        [
            _waypoint("wp1"),
            _waypoint("wp2", 0.001),
            _waypoint("wp3", 0.002),
        ],
    )


def _upload_messages(item_count: int) -> list[FakeMessage]:
    return [
        *(
            FakeMessage("MISSION_REQUEST_INT", seq=sequence)
            for sequence in range(item_count)
        ),
        FakeMessage("MISSION_ACK", type=FakeMavlink.MAV_MISSION_ACCEPTED),
    ]


def _connected_adapter(
    connection: FakeConnection | None = None,
) -> tuple[StubbedArduPilotSitlAdapter, FakeConnection]:
    resolved_connection = connection or FakeConnection()
    adapter = StubbedArduPilotSitlAdapter(resolved_connection)
    adapter.connect()
    return adapter, resolved_connection


def _vehicle() -> VehicleProfile:
    vehicle, _document = load_vehicle(VEHICLE_PATH)
    return vehicle


def _document(name: str) -> InputDocument:
    return InputDocument(
        path=Path(name),
        format="yaml",
        sha256="0" * 64,
    )


def _scenario_envelope() -> ScenarioResultEnvelope:
    scenario_document = _document("scenario.yaml")
    mission_document = _document("mission.yaml")
    vehicle_document = _document("vehicle.yaml")
    return build_scenario_envelope(
        result=ScenarioResult(
            scenario_id="test-scenario",
            status=ScenarioStatus.PASSED,
        ),
        scenario_document=scenario_document,
        mission_document=mission_document,
        vehicle_document=vehicle_document,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mission_action_to_mavlink_cmd_waypoint() -> None:
    assert mission_action_to_mavlink_cmd(MissionAction.WAYPOINT) == 16


def test_mission_action_to_mavlink_cmd_vtol_takeoff() -> None:
    assert mission_action_to_mavlink_cmd(MissionAction.VTOL_TAKEOFF) == 84


def test_mission_action_to_mavlink_cmd_rtl() -> None:
    assert mission_action_to_mavlink_cmd(MissionAction.RTL) == 20


def test_all_mission_action_to_mavlink_cmd_mappings_are_present() -> None:
    assert mission_action_to_mavlink_cmd(MissionAction.TAKEOFF) == 22
    assert mission_action_to_mavlink_cmd(MissionAction.LOITER_TIME) == 19
    assert mission_action_to_mavlink_cmd(MissionAction.LAND) == 21


def test_altitude_reference_to_mavlink_frame_relative() -> None:
    assert altitude_reference_to_mavlink_frame(AltitudeReference.RELATIVE_HOME) == 3


def test_altitude_reference_to_mavlink_frame_amsl() -> None:
    assert altitude_reference_to_mavlink_frame(AltitudeReference.AMSL) == 0


def test_altitude_reference_to_mavlink_frame_terrain() -> None:
    assert altitude_reference_to_mavlink_frame(AltitudeReference.TERRAIN) == 10


def test_connect_calls_heartbeat_wait() -> None:
    connection = FakeConnection()
    adapter = StubbedArduPilotSitlAdapter(connection)

    adapter.connect()

    assert connection.heartbeat_requested is True
    assert connection.connection_string == "tcp:127.0.0.1:5760"


def test_connect_closes_connection_when_heartbeat_times_out() -> None:
    connection = MissingHeartbeatConnection()
    adapter = StubbedArduPilotSitlAdapter(connection)

    with pytest.raises(ArduPilotAdapterError, match="Timed out waiting"):
        adapter.connect()

    assert connection.closed is True
    assert adapter.simulator_metadata(_vehicle()).metadata["connected"] is False


def test_upload_mission_sends_correct_item_count() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)

    adapter.upload_mission(_three_item_mission())

    assert connection.mav.mission_counts[0][2] == 3


def test_upload_mission_returns_acknowledged_result() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)

    result = adapter.upload_mission(_three_item_mission())

    assert result == MissionUploadResult(item_count=3, acknowledged=True)


def test_arm_and_start_requires_armed_heartbeat() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.append(FakeMessage("HEARTBEAT", base_mode=128))

    adapter.arm_and_start()

    assert connection.mav.command_longs
    assert connection.mode == "AUTO"


def test_arm_and_start_drains_stale_mission_progress_before_auto() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("HEARTBEAT", base_mode=128),
            FakeMessage("MISSION_CURRENT", seq=65_535, mission_state=5),
        ]
    )

    adapter.arm_and_start()

    assert connection.messages == []
    assert connection.mode == "AUTO"


def test_arm_and_start_times_out_without_armed_heartbeat() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    adapter.config = ArduPilotSitlConfig(arm_timeout_s=0.001)

    with pytest.raises(ArduPilotAdapterError, match="Timed out waiting"):
        adapter.arm_and_start()


def test_unsupported_action_raises_adapter_error() -> None:
    adapter, _connection = _connected_adapter()
    route_item = RouteItem.model_construct(
        id="unsupported",
        action="fly_sideways",
        lat=None,
        lon=None,
        altitude_m=None,
        altitude_reference=None,
        loiter_time_s=None,
        acceptance_radius_m=None,
    )
    mission = MissionPlan.model_construct(
        defaults=MissionDefaults(
            altitude_reference=AltitudeReference.RELATIVE_HOME,
        ),
        route=[route_item],
    )

    with pytest.raises(ArduPilotAdapterError, match="fly_sideways"):
        adapter.upload_mission(mission)


def test_disconnect_closes_connection() -> None:
    adapter, connection = _connected_adapter()

    adapter.disconnect()

    assert connection.closed is True


def test_disconnect_records_target_ids_before_closing(tmp_path: Path) -> None:
    adapter, _connection = _connected_adapter()
    adapter.start_recording(tmp_path)

    adapter.disconnect()
    observed = adapter.flush_artifacts()

    simulator_log_path = Path(observed.simulator_logs[0].path)
    events = json.loads(simulator_log_path.read_text(encoding="utf-8"))["events"]
    disconnected = [event for event in events if event["event"] == "disconnected"]
    assert disconnected[0]["fields"]["target_component"] == 1
    assert disconnected[0]["fields"]["target_system"] == 1


def test_disconnect_flushes_dirty_failure_evidence(tmp_path: Path) -> None:
    adapter, _connection = _connected_adapter()
    adapter.start_recording(tmp_path)

    adapter.disconnect()

    observed = adapter.observed_artifacts()
    assert observed.adapter_logs
    assert observed.simulator_logs
    assert (tmp_path / "adapter_log.json").exists()
    assert (tmp_path / "simulator_log.json").exists()


def test_simulator_metadata_adapter_kind_is_ardupilot() -> None:
    metadata = ArduPilotSitlAdapter().simulator_metadata(_vehicle())

    assert metadata.adapter_kind == SitlAdapterKind.ARDUPILOT


def test_simulator_metadata_execution_mode_is_live_sitl() -> None:
    connection = FakeConnection()
    adapter = StubbedArduPilotSitlAdapter(connection)
    adapter.connect()

    metadata = adapter.simulator_metadata(_vehicle())

    assert metadata.execution_mode == "live_sitl"


def test_observed_artifacts_are_empty_in_ticket_041() -> None:
    observed = ArduPilotSitlAdapter().observed_artifacts()

    assert observed.telemetry == []
    assert observed.command_logs == []
    assert observed.simulator_logs == []
    assert observed.adapter_logs == []


def test_observed_artifacts_before_write_does_not_create_files(tmp_path: Path) -> None:
    adapter = ArduPilotSitlAdapter()
    adapter.start_recording(tmp_path)

    observed = adapter.observed_artifacts()

    assert observed == type(observed)()
    assert list(tmp_path.iterdir()) == []


def test_flush_artifacts_before_start_recording_raises_adapter_error() -> None:
    adapter = ArduPilotSitlAdapter()

    with pytest.raises(ArduPilotAdapterError, match="recording is not configured"):
        adapter.flush_artifacts()


def test_start_recording_twice_raises_adapter_error(tmp_path: Path) -> None:
    adapter = ArduPilotSitlAdapter()
    adapter.start_recording(tmp_path)

    with pytest.raises(ArduPilotAdapterError, match="already configured"):
        adapter.start_recording(tmp_path / "second")


def test_adapter_records_telemetry_and_command_artifacts(tmp_path: Path) -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter = StubbedArduPilotSitlAdapter(connection)
    adapter.start_recording(tmp_path)
    adapter.connect()
    adapter.upload_mission(_three_item_mission())
    connection.messages.append(FakeMessage("MISSION_CURRENT", seq=2))

    observed = adapter.record_telemetry(sample_count=1)

    assert observed.telemetry[0].path.endswith("telemetry.json")
    assert observed.command_logs[0].path.endswith("command_log.json")
    assert observed.simulator_logs[0].path.endswith("simulator_log.json")
    assert observed.adapter_logs[0].path.endswith("adapter_log.json")


def test_disconnect_refreshes_previously_returned_observed_hashes(
    tmp_path: Path,
) -> None:
    connection = FakeConnection([FakeMessage("MISSION_CURRENT", seq=0)])
    adapter = StubbedArduPilotSitlAdapter(connection)
    adapter.start_recording(tmp_path)
    adapter.connect()

    observed = adapter.record_telemetry(sample_count=1)
    simulator_log_path = Path(observed.simulator_logs[0].path)
    original_hash = observed.simulator_logs[0].sha256
    adapter.disconnect()

    assert observed.simulator_logs[0].sha256 == _sha256(simulator_log_path)
    assert observed.simulator_logs[0].sha256 != original_hash
    events = json.loads(simulator_log_path.read_text(encoding="utf-8"))["events"]
    assert [event["event"] for event in events] == ["connected", "disconnected"]


def test_missing_telemetry_raises_explicit_adapter_error(tmp_path: Path) -> None:
    adapter, _connection = _connected_adapter()
    adapter.start_recording(tmp_path)

    with pytest.raises(ArduPilotAdapterError, match="Timed out waiting"):
        adapter.record_telemetry(sample_count=1, timeout_s=0.01)


def test_wait_for_mission_complete_requires_completion_evidence() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=2),
            FakeMessage("MISSION_ITEM_REACHED", seq=2),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.1).value == "complete"


def test_wait_for_mission_complete_aborts_on_stalled_sequence() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    adapter.config = ArduPilotSitlConfig(mission_stall_timeout_s=0.01)
    connection.messages.extend(
        FakeMessage("MISSION_CURRENT", seq=0, mission_state=3) for _ in range(50)
    )

    assert adapter.wait_for_mission_complete(timeout_s=5.0).value == "timeout"


def test_wait_for_mission_complete_sequence_advance_defers_stall() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    adapter.config = ArduPilotSitlConfig(mission_stall_timeout_s=10.0)
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=0, mission_state=3),
            FakeMessage("MISSION_CURRENT", seq=1, mission_state=3),
            FakeMessage("MISSION_ITEM_REACHED", seq=2),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=5.0).value == "complete"


def test_wait_for_mission_complete_accepts_mavlink2_complete_state() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=0, mission_state=3),
            FakeMessage("MISSION_CURRENT", seq=2, mission_state=5),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.1).value == "complete"


def test_wait_for_mission_complete_rejects_explicit_active_state_with_stale_seq() -> (
    None
):
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.append(
        FakeMessage("MISSION_CURRENT", seq=65_535, mission_state=3)
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.001).value == "timeout"


def test_wait_for_mission_complete_accepts_exact_legacy_one_past_sequence() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=0),
            FakeMessage("MISSION_CURRENT", seq=3),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.1).value == "complete"


def test_wait_for_mission_complete_accepts_unknown_state_one_past_sequence() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=0, mission_state=0),
            FakeMessage("MISSION_CURRENT", seq=3, mission_state=0),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.1).value == "complete"


def test_wait_for_mission_complete_rejects_legacy_uint16_max_sequence() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.append(FakeMessage("MISSION_CURRENT", seq=65_535))

    assert adapter.wait_for_mission_complete(timeout_s=0.001).value == "timeout"


def test_wait_for_mission_complete_rejects_final_item_selection() -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.upload_mission(_three_item_mission())
    connection.messages.append(FakeMessage("MISSION_CURRENT", seq=2))

    assert adapter.wait_for_mission_complete(timeout_s=0.001).value == "timeout"


def test_wait_for_mission_complete_ignores_late_stale_complete_until_progress(
    tmp_path: Path,
) -> None:
    connection = FakeConnection(_upload_messages(item_count=3))
    adapter, _connection = _connected_adapter(connection)
    adapter.start_recording(tmp_path)
    adapter.upload_mission(_three_item_mission())
    connection.messages.extend(
        [
            FakeMessage("MISSION_CURRENT", seq=2, mission_state=5),
            FakeMessage("MISSION_CURRENT", seq=0, mission_state=3),
            FakeMessage("MISSION_ITEM_REACHED", seq=2),
        ]
    )

    assert adapter.wait_for_mission_complete(timeout_s=0.1).value == "complete"
    observed = adapter.flush_artifacts()
    adapter_log = json.loads(
        Path(observed.adapter_logs[0].path).read_text(encoding="utf-8")
    )
    events = [event["event"] for event in adapter_log["events"]]
    assert "mission_completion_ignored" in events
    assert events.index("mission_completion_ignored") < events.index(
        "mission_progress_verified"
    )


def test_adapter_satisfies_sitl_adapter_protocol() -> None:
    adapter = ArduPilotSitlAdapter()
    required_attributes = ("adapter_id", "adapter_kind", "adapter_version")
    required_methods = ("simulator_metadata", "observed_artifacts")

    for name in required_attributes:
        assert hasattr(adapter, name)
    for name in required_methods:
        assert callable(getattr(adapter, name))
    assert adapter.adapter_kind == SitlAdapterKind.ARDUPILOT


def test_ardupilot_adapter_plugs_into_build_sitl_evidence_bundle() -> None:
    adapter, _connection = _connected_adapter()
    scenario_document = _document("scenario.yaml")
    mission_document = _document("mission.yaml")
    vehicle_document = _document("vehicle.yaml")

    bundle = build_sitl_evidence_bundle(
        evidence_id="test-evidence",
        scenario_envelope=_scenario_envelope(),
        scenario_document=scenario_document,
        mission_document=mission_document,
        vehicle_document=vehicle_document,
        vehicle=_vehicle(),
        adapter=adapter,
    )

    assert bundle.simulator.adapter_kind == SitlAdapterKind.ARDUPILOT
    assert bundle.status == SitlEvidenceStatus.ERROR
