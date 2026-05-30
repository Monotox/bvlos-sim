"""File I/O helpers for phase segment result artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from adapters.canonical_json import render_canonical_json
from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from schemas.phase_segment import PhaseSegmentResult


def write_phase_segments(result: PhaseSegmentResult, path: Path) -> None:
    """Write a phase segment result to a JSON file with canonical formatting."""
    payload = result.model_dump(mode="json")
    path.write_text(render_canonical_json(payload), encoding="utf-8")


def load_phase_segments(path: Path) -> tuple[PhaseSegmentResult, InputDocument]:
    """Load a phase segment result, returning the model and its InputDocument.

    Raises InputLoadError on read, parse, or validation failure.
    """
    parsed, document = read_and_parse_document(path, input_name="phase_segments")
    payload = validate_mapping_root(parsed, input_name="phase_segments", path=path)
    try:
        return PhaseSegmentResult.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Phase segment file failed schema validation.",
            input_name="phase_segments",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


__all__ = [
    "load_phase_segments",
    "write_phase_segments",
]
