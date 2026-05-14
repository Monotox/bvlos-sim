"""Tests for the ArduPilot SITL adapter (Ticket 041)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.ardupilot_sitl import (
    ArduPilotAdapterError,
    ArduPilotSitlAdapter,
    MissionUploadResult,
    altitude_reference_to_mavlink_frame,
    mission_action_to_mavlink_cmd,
)
from adapters.io import InputDocument, load_vehicle
from adapters.scenario_envelope import ScenarioResultEnvelope, build_scenario_envelope
from adapters.sitl_evidence import build_sitl_evidence_bundle
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
    assert bundle.status == SitlEvidenceStatus.CONTRACT_ONLY
