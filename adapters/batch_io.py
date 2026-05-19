"""Batch manifest loading for multi-run estimate workflows."""

from pathlib import Path

from pydantic import ValidationError

from adapters.io import (
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from schemas.batch import BatchManifest, BatchRun


def _resolve_manifest_path(path: Path, *, manifest_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return manifest_dir / path


def _resolve_run_paths(run: BatchRun, *, manifest_dir: Path) -> BatchRun:
    return run.model_copy(
        update={
            "mission": _resolve_manifest_path(run.mission, manifest_dir=manifest_dir),
            "vehicle": _resolve_manifest_path(run.vehicle, manifest_dir=manifest_dir),
        }
    )


def load_batch_manifest(path: Path) -> BatchManifest:
    """Load and validate a batch.v1 manifest YAML or JSON file."""
    parsed, document = read_and_parse_document(path, input_name="batch")
    payload = validate_mapping_root(parsed, input_name="batch", path=path)
    try:
        manifest = BatchManifest.model_validate(payload)
    except ValidationError as exc:
        raise InputLoadError(
            "Batch manifest failed schema validation.",
            input_name="batch",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc

    runs = [
        _resolve_run_paths(run, manifest_dir=path.parent) for run in manifest.runs
    ]
    return manifest.model_copy(update={"runs": runs})
