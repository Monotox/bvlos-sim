"""Public value types for the ArduPilot SITL adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class ArduPilotSitlConfig:
    host: str = "127.0.0.1"
    port: int = 5760
    connection_timeout_s: float = 30.0
    mission_upload_timeout_s: float = 60.0
    arm_timeout_s: float = 90.0
    mission_stall_timeout_s: float = 240.0


@dataclass(frozen=True)
class MissionUploadResult:
    item_count: int
    acknowledged: bool


class RunState(StrEnum):
    COMPLETE = "complete"
    TIMEOUT = "timeout"
    ERROR = "error"


class ArduPilotAdapterError(RuntimeError):
    pass


__all__ = [
    "ArduPilotAdapterError",
    "ArduPilotSitlConfig",
    "MissionUploadResult",
    "RunState",
]
