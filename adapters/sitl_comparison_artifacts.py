"""Artifact-record loading for SITL comparison reports."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from schemas.sitl import SitlArtifactReference

type ArtifactRecord = Mapping[str, object]


@dataclass(frozen=True)
class ArtifactRecords:
    records: list[ArtifactRecord]
    note: str | None = None


class SitlArtifactLogReader:
    """Read already-written SITL artifact logs."""

    def records(
        self,
        references: Sequence[SitlArtifactReference],
        payload_key: str,
    ) -> ArtifactRecords:
        if not references:
            return ArtifactRecords(
                [],
                f"No {payload_key} artifact reference was present.",
            )
        try:
            payload = json.loads(Path(references[0].path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return ArtifactRecords([], f"Could not read {payload_key} artifact: {exc}")

        value = payload.get(payload_key)
        if not isinstance(value, list):
            return ArtifactRecords(
                [],
                f"Artifact did not contain a list payload at '{payload_key}'.",
            )
        return ArtifactRecords(list_of_mappings(value))


def list_of_mappings(value: object) -> list[ArtifactRecord]:
    return (
        [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, list)
        else []
    )


def first_record_with(
    records: Sequence[ArtifactRecord],
    field_name: str,
    field_value: object,
) -> ArtifactRecord | None:
    return next(
        (record for record in records if record.get(field_name) == field_value),
        None,
    )


def has_record_with(
    records: Sequence[ArtifactRecord],
    field_name: str,
    field_value: object,
) -> bool:
    return first_record_with(records, field_name, field_value) is not None


__all__ = [
    "ArtifactRecord",
    "ArtifactRecords",
    "SitlArtifactLogReader",
    "first_record_with",
    "has_record_with",
    "list_of_mappings",
]
