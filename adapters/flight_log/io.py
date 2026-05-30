"""File I/O helpers for normalized flight trace artifacts."""

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
from schemas.flight_log import NormalizedFlightTrace


def write_flight_trace(trace: NormalizedFlightTrace, path: Path) -> None:
    """Write a normalized flight trace to a JSON file with canonical formatting."""
    payload = trace.model_dump(mode="json")
    path.write_text(render_canonical_json(payload), encoding="utf-8")


def read_flight_trace(path: Path) -> NormalizedFlightTrace:
    """Read and validate a normalized flight trace from a JSON file.

    Raises InputLoadError on parse or validation failure.
    """
    trace, _ = load_flight_trace(path)
    return trace


def load_flight_trace(path: Path) -> tuple[NormalizedFlightTrace, InputDocument]:
    """Load a normalized flight trace, returning the model and its InputDocument.

    Raises InputLoadError on read, parse, or validation failure.
    """
    parsed, document = read_and_parse_document(path, input_name="flight_trace")
    payload = validate_mapping_root(parsed, input_name="flight_trace", path=path)
    try:
        return NormalizedFlightTrace.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Flight trace file failed schema validation.",
            input_name="flight_trace",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


__all__ = [
    "load_flight_trace",
    "read_flight_trace",
    "write_flight_trace",
]
