"""Telemetry and lifecycle comparison dimensions for SITL reports."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from adapters.sitl_comparison_artifacts import (
    _ArtifactRecords,
    _SitlArtifactLogReader,
    _first_record_with,
    _has_record_with,
    _list_of_mappings,
)
from adapters.sitl_comparison_values import _SitlComparisonValueCoercer
from schemas.sitl import SitlEvidenceBundle
from schemas.sitl_comparison import SitlComparisonItem, SitlComparisonOutcome

_MISSION_COUNT_TOLERANCE = 2


@dataclass(frozen=True)
class _SitlTelemetryComparisonBuilder:
    """Build comparisons from observed telemetry and lifecycle logs."""

    reader: _SitlArtifactLogReader = field(default_factory=_SitlArtifactLogReader)
    values: _SitlComparisonValueCoercer = field(
        default_factory=_SitlComparisonValueCoercer,
    )

    def telemetry_records(self, bundle: SitlEvidenceBundle) -> _ArtifactRecords:
        return self.reader.records(bundle.observed.telemetry, "records")

    def items(
        self,
        bundle: SitlEvidenceBundle,
        scenario_report: Mapping[str, object],
        telemetry: _ArtifactRecords,
    ) -> list[SitlComparisonItem]:
        return [
            self._mission_item_count_item(bundle, scenario_report),
            self._telemetry_record_count_item(telemetry),
            self._heartbeat_observed_item(telemetry),
            self._adapter_lifecycle_item(bundle),
            self._simulator_lifecycle_item(bundle),
        ]

    def _mission_item_count_item(
        self,
        bundle: SitlEvidenceBundle,
        scenario_report: Mapping[str, object],
    ) -> SitlComparisonItem:
        command_log = self.reader.records(bundle.observed.command_logs, "commands")
        expected = self._expected_mission_item_count(scenario_report)
        record = _first_record_with(command_log.records, "command", "MISSION_COUNT")
        if record is None:
            return self._missing_mission_count_item(
                expected,
                command_log.note or "MISSION_COUNT command was not found.",
            )

        item_count = self.values.integer_field(record.get("fields"), "item_count")
        if item_count is None:
            return self._missing_mission_count_item(
                expected,
                "MISSION_COUNT command did not include integer fields.item_count.",
            )

        return SitlComparisonItem(
            dimension="mission_item_count",
            outcome=self._mission_item_count_outcome(expected, item_count),
            expected=expected,
            observed=item_count,
            tolerance=_MISSION_COUNT_TOLERANCE,
        )

    def _expected_mission_item_count(
        self,
        scenario_report: Mapping[str, object],
    ) -> int:
        return max(0, len(_list_of_mappings(scenario_report.get("timeline"))) - 1)

    def _missing_mission_count_item(
        self,
        expected: int,
        note: str,
    ) -> SitlComparisonItem:
        return SitlComparisonItem(
            dimension="mission_item_count",
            outcome=SitlComparisonOutcome.MISSING,
            expected=expected,
            observed=None,
            tolerance=_MISSION_COUNT_TOLERANCE,
            notes=note,
        )

    def _mission_item_count_outcome(
        self,
        expected: int,
        observed: int,
    ) -> SitlComparisonOutcome:
        return (
            SitlComparisonOutcome.MATCHED
            if observed == expected
            else SitlComparisonOutcome.DRIFTED
        )

    def _telemetry_record_count_item(
        self,
        telemetry: _ArtifactRecords,
    ) -> SitlComparisonItem:
        count = len(telemetry.records)
        return SitlComparisonItem(
            dimension="telemetry_record_count",
            outcome=self._presence_outcome(count > 0),
            expected={">": 0},
            observed=count,
            notes=telemetry.note,
        )

    def _heartbeat_observed_item(
        self,
        telemetry: _ArtifactRecords,
    ) -> SitlComparisonItem:
        found = _has_record_with(telemetry.records, "message_type", "HEARTBEAT")
        return SitlComparisonItem(
            dimension="heartbeat_observed",
            outcome=self._presence_outcome(found),
            expected=True,
            observed=found,
            notes=self._missing_note(
                found,
                telemetry.note or "HEARTBEAT telemetry was not observed.",
            ),
        )

    def _adapter_lifecycle_item(
        self,
        bundle: SitlEvidenceBundle,
    ) -> SitlComparisonItem:
        adapter_log = self.reader.records(bundle.observed.adapter_logs, "events")
        events = {str(record.get("event")) for record in adapter_log.records}
        required = frozenset({"adapter_initialized", "recording_started"})
        present = sorted(required & events)
        return SitlComparisonItem(
            dimension="adapter_lifecycle",
            outcome=self._lifecycle_outcome(len(present), len(required)),
            expected=sorted(required),
            observed=present,
            notes=adapter_log.note,
        )

    def _simulator_lifecycle_item(
        self,
        bundle: SitlEvidenceBundle,
    ) -> SitlComparisonItem:
        simulator_log = self.reader.records(bundle.observed.simulator_logs, "events")
        found = _has_record_with(simulator_log.records, "event", "connected")
        return SitlComparisonItem(
            dimension="simulator_lifecycle",
            outcome=self._presence_outcome(found),
            expected="connected",
            observed="connected" if found else None,
            notes=self._missing_note(found, simulator_log.note),
        )

    def _presence_outcome(self, found: bool) -> SitlComparisonOutcome:
        return SitlComparisonOutcome.MATCHED if found else SitlComparisonOutcome.MISSING

    def _lifecycle_outcome(
        self,
        present_count: int,
        required_count: int,
    ) -> SitlComparisonOutcome:
        rules = (
            (present_count == required_count, SitlComparisonOutcome.MATCHED),
            (present_count > 0, SitlComparisonOutcome.DRIFTED),
        )
        return next(
            (outcome for applies, outcome in rules if applies),
            SitlComparisonOutcome.MISSING,
        )

    def _missing_note(self, found: bool, note: str | None) -> str | None:
        return None if found else note


__all__: list[str] = []
