"""File I/O helpers for validation report artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from adapters.atomic_write import atomic_write_text
from adapters.canonical_json import render_canonical_json
from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from schemas.validation import ValidationReport


def write_validation_report(report: ValidationReport, path: Path) -> None:
    """Write a validation report to a JSON file with canonical formatting."""
    payload = report.model_dump(mode="json")
    atomic_write_text(path, render_canonical_json(payload))


def load_validation_report(path: Path) -> tuple[ValidationReport, InputDocument]:
    """Load a validation report, returning the model and its InputDocument.

    Raises InputLoadError on read, parse, or validation failure.
    """
    parsed, document = read_and_parse_document(path, input_name="validation_report")
    payload = validate_mapping_root(parsed, input_name="validation_report", path=path)
    try:
        return ValidationReport.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Validation report file failed schema validation.",
            input_name="validation_report",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


__all__ = [
    "load_validation_report",
    "write_validation_report",
]
