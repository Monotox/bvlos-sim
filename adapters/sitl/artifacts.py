"""Artifact recording helpers for SITL evidence bundles."""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from schemas.sitl import (
    SitlArtifactReference,
    SitlArtifactRole,
    SitlObservedArtifacts,
)

SITL_TELEMETRY_SCHEMA_VERSION = "sitl-telemetry.v1"
SITL_COMMAND_LOG_SCHEMA_VERSION = "sitl-command-log.v1"
SITL_SIMULATOR_LOG_SCHEMA_VERSION = "sitl-simulator-log.v1"
SITL_ADAPTER_LOG_SCHEMA_VERSION = "sitl-adapter-log.v1"


class SitlArtifactError(RuntimeError):
    pass


type SitlArtifactValue = (
    str
    | int
    | float
    | bool
    | None
    | list["SitlArtifactValue"]
    | dict[str, "SitlArtifactValue"]
)


@dataclass(frozen=True)
class SitlArtifactSet:
    telemetry: Path
    command_log: Path
    simulator_log: Path
    adapter_log: Path


@dataclass
class SitlArtifactRecorder:
    artifact_dir: Path
    telemetry_records: list[dict[str, SitlArtifactValue]] = field(default_factory=list)
    command_records: list[dict[str, SitlArtifactValue]] = field(default_factory=list)
    simulator_events: list[dict[str, SitlArtifactValue]] = field(default_factory=list)
    adapter_events: list[dict[str, SitlArtifactValue]] = field(default_factory=list)
    _observed_artifacts: SitlObservedArtifacts | None = field(
        init=False,
        default=None,
        repr=False,
    )
    _dirty: bool = field(init=False, default=True, repr=False)

    def record_telemetry_message(self, timestamp_s: float, message: object) -> None:
        self.telemetry_records.append(
            {
                "timestamp_s": timestamp_s,
                "message_type": _message_type(message),
                "fields": _message_fields(message),
            }
        )
        self._dirty = True

    def record_command(
        self,
        timestamp_s: float,
        command: str,
        fields: Mapping[str, SitlArtifactValue] | None = None,
    ) -> None:
        self.command_records.append(
            {
                "timestamp_s": timestamp_s,
                "command": command,
                "fields": _normalize_mapping(fields or {}),
            }
        )
        self._dirty = True

    def record_simulator_event(
        self,
        timestamp_s: float,
        event: str,
        fields: Mapping[str, SitlArtifactValue] | None = None,
    ) -> None:
        self.simulator_events.append(
            {
                "timestamp_s": timestamp_s,
                "event": event,
                "fields": _normalize_mapping(fields or {}),
            }
        )
        self._dirty = True

    def record_adapter_event(
        self,
        timestamp_s: float,
        event: str,
        fields: Mapping[str, SitlArtifactValue] | None = None,
    ) -> None:
        self.adapter_events.append(
            {
                "timestamp_s": timestamp_s,
                "event": event,
                "fields": _normalize_mapping(fields or {}),
            }
        )
        self._dirty = True

    @property
    def observed(self) -> SitlObservedArtifacts | None:
        if self._dirty:
            return None
        return self._observed_artifacts

    def write(self) -> SitlObservedArtifacts:
        """Write all recorded artifacts to disk and return the observed-artifacts object.

        The same ``SitlObservedArtifacts`` instance is returned on every call.
        Callers that hold a reference to a previous return value will see its
        fields updated in-place after subsequent writes — do not cache the
        result across mutating record_* calls unless that behaviour is intended.
        """
        if self._observed_artifacts is not None and not self._dirty:
            return self._observed_artifacts

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifacts = SitlArtifactSet(
            telemetry=self.artifact_dir / "telemetry.json",
            command_log=self.artifact_dir / "command_log.json",
            simulator_log=self.artifact_dir / "simulator_log.json",
            adapter_log=self.artifact_dir / "adapter_log.json",
        )
        telemetry = _write_artifact_reference(
            artifacts.telemetry,
            SITL_TELEMETRY_SCHEMA_VERSION,
            "records",
            self.telemetry_records,
            role=SitlArtifactRole.TELEMETRY,
            description="Normalized MAVLink telemetry records.",
        )
        command_log = _write_artifact_reference(
            artifacts.command_log,
            SITL_COMMAND_LOG_SCHEMA_VERSION,
            "commands",
            self.command_records,
            role=SitlArtifactRole.COMMAND_LOG,
            description="MAVLink commands emitted by the adapter.",
        )
        simulator_log = _write_artifact_reference(
            artifacts.simulator_log,
            SITL_SIMULATOR_LOG_SCHEMA_VERSION,
            "events",
            self.simulator_events,
            role=SitlArtifactRole.SIMULATOR_LOG,
            description="SITL simulator lifecycle events.",
        )
        adapter_log = _write_artifact_reference(
            artifacts.adapter_log,
            SITL_ADAPTER_LOG_SCHEMA_VERSION,
            "events",
            self.adapter_events,
            role=SitlArtifactRole.ADAPTER_LOG,
            description="Adapter lifecycle events.",
        )
        observed = SitlObservedArtifacts(
            telemetry=[telemetry] if telemetry is not None else [],
            command_logs=[command_log] if command_log is not None else [],
            simulator_logs=[simulator_log] if simulator_log is not None else [],
            adapter_logs=[adapter_log] if adapter_log is not None else [],
        )
        self._cache_observed_artifacts(observed)
        if self._observed_artifacts is None:
            raise AssertionError("SITL artifact cache was not initialized")
        return self._observed_artifacts

    def _cache_observed_artifacts(self, observed: SitlObservedArtifacts) -> None:
        if self._observed_artifacts is None:
            self._observed_artifacts = observed
        else:
            self._observed_artifacts.telemetry = observed.telemetry
            self._observed_artifacts.command_logs = observed.command_logs
            self._observed_artifacts.simulator_logs = observed.simulator_logs
            self._observed_artifacts.adapter_logs = observed.adapter_logs
        self._dirty = False


def _message_type(message: object) -> str:
    get_type = getattr(message, "get_type", None)
    if callable(get_type):
        value = get_type()
        if isinstance(value, str) and value:
            return value

    value = getattr(message, "message_type", None)
    if isinstance(value, str) and value:
        return value
    raise SitlArtifactError(
        "Telemetry message does not expose a non-empty MAVLink message type "
        "via get_type() or message_type",
    )


def _message_fields(message: object) -> dict[str, SitlArtifactValue]:
    to_dict = getattr(message, "to_dict", None)
    if callable(to_dict):
        try:
            value = to_dict()
        except Exception as exc:
            raise SitlArtifactError(
                f"Telemetry message to_dict() failed: {exc}",
            ) from exc
        if isinstance(value, Mapping):
            return _normalize_mapping(value)
        raise SitlArtifactError(
            "Telemetry message to_dict() did not return a mapping "
            f"(got {type(value).__name__})",
        )

    public_fields = {
        name: value
        for name, value in vars(message).items()
        if not name.startswith("_") and name != "message_type"
    }
    if not public_fields:
        raise SitlArtifactError("Telemetry message does not expose replayable fields")
    return _normalize_mapping(public_fields)


def _normalize_mapping(
    mapping: Mapping[object, object],
) -> dict[str, SitlArtifactValue]:
    return {
        str(key): _normalize_value(value)
        for key, value in sorted(mapping.items(), key=lambda item: str(item[0]))
    }


def _normalize_value(value: object) -> SitlArtifactValue:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise SitlArtifactError(f"Artifact field value is not finite: {value!r}")
        return value
    if isinstance(value, Mapping):
        return _normalize_mapping(value)
    if isinstance(value, list | tuple):
        return [_normalize_value(item) for item in value]
    raise SitlArtifactError(
        f"Artifact field value is not JSON-serializable: {type(value).__name__}",
    )


def _write_artifact(
    path: Path,
    schema_version: str,
    payload_key: str,
    payload: list[dict[str, SitlArtifactValue]],
) -> None:
    content = {
        "schema_version": schema_version,
        payload_key: payload,
    }
    path.write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_artifact_reference(
    path: Path,
    schema_version: str,
    payload_key: str,
    payload: list[dict[str, SitlArtifactValue]],
    *,
    role: SitlArtifactRole,
    description: str,
) -> SitlArtifactReference | None:
    if not payload:
        return None
    _write_artifact(path, schema_version, payload_key, payload)
    return _reference(
        path,
        role=role,
        schema_version=schema_version,
        description=description,
    )


def _reference(
    path: Path,
    *,
    role: SitlArtifactRole,
    schema_version: str,
    description: str,
) -> SitlArtifactReference:
    return SitlArtifactReference(
        role=role,
        path=str(path),
        format="json",
        sha256=_sha256(path),
        schema_version=schema_version,
        description=description,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "SITL_ADAPTER_LOG_SCHEMA_VERSION",
    "SITL_COMMAND_LOG_SCHEMA_VERSION",
    "SITL_SIMULATOR_LOG_SCHEMA_VERSION",
    "SITL_TELEMETRY_SCHEMA_VERSION",
    "SitlArtifactError",
    "SitlArtifactRecorder",
    "SitlArtifactSet",
    "SitlArtifactValue",
]
