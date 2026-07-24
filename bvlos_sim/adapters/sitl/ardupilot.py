"""ArduPilot SITL mission-execution and evidence adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep
from typing import ClassVar, cast

from bvlos_sim.adapters.sitl.artifacts import SitlArtifactRecorder
from bvlos_sim.adapters.sitl.ardupilot_mavlink import (
    RUN_STATE_MESSAGE_TYPES,
    MavConnection,
    MavutilModule,
    arm_with_retry,
    drain_mission_progress_messages,
    heartbeat_indicates_rtl,
    message_sequence,
    message_type,
    mission_execution_complete,
    mission_execution_progressed,
    set_auto_mode,
)
from bvlos_sim.adapters.sitl.ardupilot_mission import (
    ALTITUDE_REFERENCE_TO_MAVLINK_FRAME,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MISSION_ACTION_TO_MAVLINK_CMD,
    MissionLike,
    altitude_reference_to_mavlink_frame,
    build_mission_items,
    mission_action_to_mavlink_cmd,
)
from bvlos_sim.adapters.sitl.ardupilot_types import (
    ArduPilotAdapterError,
    ArduPilotSitlConfig,
    MissionUploadResult,
    RunState,
)
from bvlos_sim.adapters.sitl.ardupilot_upload import MissionUploadProtocol
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.sitl import (
    SitlAdapterKind,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)
from bvlos_sim.schemas.vehicle import VehicleProfile

_MISSION_UPLOAD_ATTEMPTS = 3
_MISSION_UPLOAD_RETRY_DELAY_S = 5.0


def _message_mission_sequence(message: object | None) -> int | None:
    """Mission sequence carried by a run-state message, if any."""
    if message is None:
        return None
    if message_type(message) not in ("MISSION_CURRENT", "MISSION_ITEM_REACHED"):
        return None
    try:
        return message_sequence(message)
    except (AttributeError, TypeError, ValueError):
        return None


@dataclass(init=False)
class ArduPilotSitlAdapter:
    config: ArduPilotSitlConfig = field(init=False)

    adapter_id: ClassVar[str] = "ardupilot-sitl-v1"
    adapter_kind: ClassVar[SitlAdapterKind] = SitlAdapterKind.ARDUPILOT
    adapter_version: ClassVar[str] = "0.1.0"

    _connection: MavConnection | None = field(init=False, default=None, repr=False)
    _heartbeat: object | None = field(init=False, default=None, repr=False)
    _mission_item_count: int | None = field(init=False, default=None, repr=False)
    _final_item_is_rtl: bool = field(init=False, default=False, repr=False)
    _run_state: RunState | None = field(init=False, default=None, repr=False)
    _artifact_recorder: SitlArtifactRecorder | None = field(
        init=False,
        default=None,
        repr=False,
    )

    def __init__(self, config: ArduPilotSitlConfig | None = None) -> None:
        self.config = config or ArduPilotSitlConfig()
        self._connection = None
        self._heartbeat = None
        self._mission_item_count = None
        self._final_item_is_rtl = False
        self._run_state = None
        self._artifact_recorder = None

    def connect(self) -> None:
        connection_string = self._connection_string()
        connection = self._open_connection(connection_string)
        try:
            heartbeat = self._wait_for_heartbeat(connection, connection_string)
        except BaseException as exc:
            try:
                connection.close()
            except Exception as close_exc:
                exc.add_note(
                    "Closing the MAVLink connection after heartbeat failure also "
                    f"failed: {close_exc}"
                )
            raise
        self._connection = connection
        self._heartbeat = heartbeat
        self._record_simulator_event(
            "connected",
            {
                "connection_string": connection_string,
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )

    def upload_mission(self, mission: MissionPlan) -> MissionUploadResult:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        items = build_mission_items(cast(MissionLike, mission))

        protocol = MissionUploadProtocol(
            timeout_s=self.config.mission_upload_timeout_s,
            command_recorder=self._record_command,
        )
        # A freshly booted SITL can reject or drop the first transfer while
        # parameters and pre-arm state are still settling; retry bounded.
        for attempt in range(1, _MISSION_UPLOAD_ATTEMPTS + 1):
            try:
                protocol.upload(connection, mavlink, items)
                break
            except ArduPilotAdapterError:
                if attempt == _MISSION_UPLOAD_ATTEMPTS:
                    raise
                sleep(_MISSION_UPLOAD_RETRY_DELAY_S)
        self._mission_item_count = len(items)
        self._final_item_is_rtl = (
            items[-1].command == MAV_CMD_NAV_RETURN_TO_LAUNCH
        )
        self._record_adapter_event("mission_uploaded", {"item_count": len(items)})
        return MissionUploadResult(item_count=len(items), acknowledged=True)

    def arm_and_start(self) -> None:
        connection = self._require_connection()
        mavlink = self._mavutil().mavlink
        self._record_command(
            "COMMAND_LONG_ARM",
            {
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )
        arm_with_retry(connection, mavlink, self.config.arm_timeout_s)
        drain_mission_progress_messages(connection)
        set_auto_mode(connection, mavlink)
        self._record_command(
            "SET_MODE_AUTO",
            {
                "target_system": connection.target_system,
                "target_component": connection.target_component,
            },
        )
        self._record_adapter_event("mission_started", {"mode": "AUTO"})

    def wait_for_mission_complete(self, timeout_s: float = 300.0) -> RunState:
        connection = self._require_connection()
        if self._mission_item_count is None:
            return self._set_run_state(RunState.ERROR)

        deadline = monotonic() + timeout_s
        final_sequence = max(0, self._mission_item_count - 1)
        current_run_progress_seen = False
        # A vehicle that enters AUTO but never advances its mission sequence
        # streams MISSION_CURRENT forever; abort well before the completion
        # deadline instead of burning the full window.
        best_sequence = -1
        last_advance = monotonic()
        while monotonic() < deadline:
            if (
                monotonic() - last_advance
                > self.config.mission_stall_timeout_s
            ):
                self._record_adapter_event(
                    "mission_stalled",
                    {
                        "best_sequence": best_sequence,
                        "stall_timeout_s": self.config.mission_stall_timeout_s,
                    },
                )
                return self._set_run_state(RunState.TIMEOUT)
            try:
                message = self._receive_run_state_message(connection)
                if message is not None and self._artifact_recorder is not None:
                    self._artifact_recorder.record_telemetry_message(
                        monotonic(), message
                    )
                completion_observed = mission_execution_complete(
                    message,
                    final_sequence=final_sequence,
                    item_count=self._mission_item_count,
                )
                if completion_observed:
                    if current_run_progress_seen:
                        return self._set_run_state(RunState.COMPLETE)
                    self._record_adapter_event(
                        "mission_completion_ignored",
                        {"reason": "no_current_run_progress"},
                    )
                    continue
                if not current_run_progress_seen and mission_execution_progressed(
                    message,
                    final_sequence=final_sequence,
                    item_count=self._mission_item_count,
                ):
                    current_run_progress_seen = True
                    self._record_adapter_event("mission_progress_verified")
                sequence = _message_mission_sequence(message)
                if sequence is not None and sequence > best_sequence:
                    best_sequence = sequence
                    last_advance = monotonic()
                # ArduPlane runs a mission RTL item by switching out of AUTO
                # into an RTL mode and loitering at home, so the final item
                # never reports reached. The handoff itself is the terminal
                # evidence once the mission has advanced to that final item.
                if (
                    self._final_item_is_rtl
                    and current_run_progress_seen
                    and best_sequence >= final_sequence
                    and heartbeat_indicates_rtl(message)
                ):
                    self._record_adapter_event(
                        "mission_completed_via_rtl_handoff",
                        {"final_sequence": final_sequence},
                    )
                    return self._set_run_state(RunState.COMPLETE)
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                return self._set_run_state(RunState.ERROR)
        return self._set_run_state(RunState.TIMEOUT)

    @property
    def run_state(self) -> RunState | None:
        """Final observed mission execution state, if a run was attempted."""

        return self._run_state

    def _set_run_state(self, state: RunState) -> RunState:
        self._run_state = state
        self._record_adapter_event("mission_run_state", {"state": state.value})
        return state

    def disconnect(self) -> None:
        connection = self._connection
        self._connection = None
        self._heartbeat = None
        close_error: Exception | None = None
        if connection is not None:
            self._record_simulator_event(
                "disconnected",
                {
                    "target_system": connection.target_system,
                    "target_component": connection.target_component,
                },
            )
            try:
                connection.close()
            except Exception as exc:
                close_error = exc

        write_error: Exception | None = None
        if self._artifact_recorder is not None:
            try:
                self._artifact_recorder.write()
            except Exception as exc:
                write_error = exc

        if close_error is not None:
            raise close_error
        if write_error is not None:
            raise write_error

    def start_recording(self, artifact_dir: Path) -> None:
        if self._artifact_recorder is not None:
            raise ArduPilotAdapterError("SITL artifact recording is already configured")
        self._artifact_recorder = SitlArtifactRecorder(artifact_dir=artifact_dir)
        self._record_adapter_event("adapter_initialized")
        self._record_adapter_event(
            "recording_started", {"artifact_dir": str(artifact_dir)}
        )

    def record_telemetry(
        self,
        *,
        sample_count: int,
        timeout_s: float = 30.0,
        message_types: Sequence[str] = RUN_STATE_MESSAGE_TYPES,
    ) -> SitlObservedArtifacts:
        if sample_count <= 0:
            raise ArduPilotAdapterError("sample_count must be greater than zero")

        connection = self._require_connection()
        recorder = self._require_artifact_recorder()
        for _ in range(sample_count):
            message = connection.recv_match(
                type=list(message_types),
                blocking=True,
                timeout=timeout_s,
            )
            if message is None:
                raise ArduPilotAdapterError("Timed out waiting for SITL telemetry")
            recorder.record_telemetry_message(monotonic(), message)
        return recorder.write()

    def flush_artifacts(self) -> SitlObservedArtifacts:
        return self._require_artifact_recorder().write()

    def simulator_metadata(self, vehicle: VehicleProfile) -> SitlSimulatorMetadata:
        connection = self._connection
        run_state = self._run_state.value if self._run_state is not None else None
        return SitlSimulatorMetadata(
            adapter_kind=self.adapter_kind,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            execution_mode=_execution_mode(connection, self._artifact_recorder),
            simulator_name="ArduPilot SITL",
            simulator_version=None,
            autopilot=_vehicle_autopilot(vehicle),
            frame=_vehicle_frame(vehicle),
            metadata={
                **_connection_metadata(self.config, connection),
                "mission_run_state": run_state,
                "mission_execution_verified": self._run_state is RunState.COMPLETE,
            },
        )

    def observed_artifacts(self) -> SitlObservedArtifacts:
        if self._artifact_recorder is None:
            return SitlObservedArtifacts()
        cached = self._artifact_recorder.observed
        if cached is None:
            return SitlObservedArtifacts()
        return cached

    def _mavutil(self) -> MavutilModule:
        try:
            from pymavlink import mavutil

            return cast(MavutilModule, mavutil)
        except ImportError as exc:
            raise ArduPilotAdapterError(
                "pymavlink is required for the ArduPilot SITL adapter. "
                "Install it with: pip install pymavlink",
            ) from exc

    def _connection_string(self) -> str:
        return f"tcp:{self.config.host}:{self.config.port}"

    def _open_connection(self, connection_string: str) -> MavConnection:
        try:
            return self._mavutil().mavlink_connection(
                connection_string,
                autoreconnect=False,
            )
        except OSError as exc:
            raise ArduPilotAdapterError(
                f"Could not connect to ArduPilot SITL at {connection_string}",
            ) from exc

    def _wait_for_heartbeat(
        self,
        connection: MavConnection,
        connection_string: str,
    ) -> object:
        heartbeat = connection.wait_heartbeat(
            timeout=self.config.connection_timeout_s,
        )
        if heartbeat is None:
            raise ArduPilotAdapterError(
                f"Timed out waiting for ArduPilot heartbeat on {connection_string}",
            )
        return heartbeat

    def _require_connection(self) -> MavConnection:
        if self._connection is None:
            raise ArduPilotAdapterError("ArduPilot SITL is not connected")
        return self._connection

    def _receive_run_state_message(
        self,
        connection: MavConnection,
    ) -> object | None:
        return connection.recv_match(
            type=list(RUN_STATE_MESSAGE_TYPES),
            blocking=True,
            timeout=1.0,
        )

    def _require_artifact_recorder(self) -> SitlArtifactRecorder:
        if self._artifact_recorder is None:
            raise ArduPilotAdapterError("SITL artifact recording is not configured")
        return self._artifact_recorder

    def _record_command(self, command: str, fields: Mapping[str, object]) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_command(monotonic(), command, fields)

    def _record_simulator_event(
        self,
        event: str,
        fields: Mapping[str, object],
    ) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_simulator_event(monotonic(), event, fields)

    def _record_adapter_event(
        self,
        event: str,
        fields: Mapping[str, object] | None = None,
    ) -> None:
        if self._artifact_recorder is None:
            return
        self._artifact_recorder.record_adapter_event(monotonic(), event, fields or {})


def _vehicle_autopilot(vehicle: VehicleProfile) -> str | None:
    if vehicle.autopilot is None:
        return None
    return vehicle.autopilot.value


def _vehicle_frame(vehicle: VehicleProfile) -> str | None:
    if vehicle.sitl is None:
        return None
    return vehicle.sitl.frame


def _connection_metadata(
    config: ArduPilotSitlConfig,
    connection: MavConnection | None,
) -> dict[str, str | int | bool | None]:
    return {
        "host": config.host,
        "port": config.port,
        "connected": connection is not None,
        "target_system": _connection_target_system(connection),
        "target_component": _connection_target_component(connection),
    }


def _execution_mode(
    connection: MavConnection | None,
    recorder: SitlArtifactRecorder | None,
) -> str:
    if connection is not None:
        return "live_sitl"
    if recorder is not None and recorder.observed is not None:
        return "live_sitl"
    return "connect_only"


def _connection_target_system(connection: MavConnection | None) -> int | None:
    if connection is None:
        return None
    return connection.target_system


def _connection_target_component(connection: MavConnection | None) -> int | None:
    if connection is None:
        return None
    return connection.target_component


__all__ = [
    "ALTITUDE_REFERENCE_TO_MAVLINK_FRAME",
    "MISSION_ACTION_TO_MAVLINK_CMD",
    "ArduPilotAdapterError",
    "ArduPilotSitlAdapter",
    "ArduPilotSitlConfig",
    "MissionUploadResult",
    "RunState",
    "altitude_reference_to_mavlink_frame",
    "mission_action_to_mavlink_cmd",
]
