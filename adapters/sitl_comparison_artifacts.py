"""Artifact-record loading for SITL comparison reports."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from schemas.sitl import SitlArtifactReference

type _ArtifactRecord = Mapping[str, object]


@dataclass(frozen=True)
class _ArtifactRecords:
    records: list[_ArtifactRecord]
    note: str | None = None


class _SitlArtifactLogReader:
    """Read already-written SITL artifact logs."""

    def records(
        self,
        references: Sequence[SitlArtifactReference],
        payload_key: str,
    ) -> _ArtifactRecords:
        if not references:
            return _ArtifactRecords(
                [],
                f"No {payload_key} artifact reference was present.",
            )
        try:
            payload = json.loads(Path(references[0].path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _ArtifactRecords([], f"Could not read {payload_key} artifact: {exc}")

        value = payload.get(payload_key)
        if not isinstance(value, list):
            return _ArtifactRecords(
                [],
                f"Artifact did not contain a list payload at '{payload_key}'.",
            )
        return _ArtifactRecords(_list_of_mappings(value))


def _list_of_mappings(value: object) -> list[_ArtifactRecord]:
    return (
        [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, list)
        else []
    )


def _first_record_with(
    records: Sequence[_ArtifactRecord],
    field_name: str,
    field_value: object,
) -> _ArtifactRecord | None:
    return next(
        (record for record in records if record.get(field_name) == field_value),
        None,
    )


def _has_record_with(
    records: Sequence[_ArtifactRecord],
    field_name: str,
    field_value: object,
) -> bool:
    return _first_record_with(records, field_name, field_value) is not None


__all__: list[str] = []
