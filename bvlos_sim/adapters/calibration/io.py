"""File I/O helpers for calibration profile artifacts."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from bvlos_sim.adapters.atomic_write import atomic_write_text
from bvlos_sim.adapters.calibration.apply import CalibrationMismatchError, apply_calibration
from bvlos_sim.adapters.canonical_json import render_canonical_json
from bvlos_sim.adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from bvlos_sim.schemas.calibration import CalibrationProfile
from bvlos_sim.schemas.vehicle import VehicleProfile


def write_calibration_profile(profile: CalibrationProfile, path: Path) -> None:
    """Write a calibration profile to a JSON file with canonical formatting."""
    payload = profile.model_dump(mode="json")
    atomic_write_text(path, render_canonical_json(payload))


def load_calibration_profile(
    path: Path,
) -> tuple[CalibrationProfile, InputDocument]:
    """Load a calibration profile, returning the model and its InputDocument.

    Raises InputLoadError on read, parse, or validation failure.
    """
    parsed, document = read_and_parse_document(path, input_name="calibration")
    payload = validate_mapping_root(parsed, input_name="calibration", path=path)
    try:
        return CalibrationProfile.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Calibration profile file failed schema validation.",
            input_name="calibration",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


def load_and_apply_calibration(
    vehicle: VehicleProfile, path: Path
) -> tuple[VehicleProfile, InputDocument]:
    """Load a calibration profile and apply it to ``vehicle``.

    CLI-facing seam shared by ``estimate``, ``scenario``, and ``validate``: it maps
    a vehicle mismatch or an override that breaks a vehicle invariant onto an
    ``InputLoadError`` so the commands' existing error handling reports it as
    invalid input. Returns the calibrated vehicle copy and the loaded document,
    so callers can record the calibration in provenance.
    """
    calibration, document = load_calibration_profile(path)
    try:
        return apply_calibration(vehicle, calibration), document
    except CalibrationMismatchError as exc:
        raise InputLoadError(
            str(exc),
            input_name="calibration",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details={
                "base_vehicle_id": exc.base_vehicle_id,
                "calibration_vehicle_id": exc.calibration_vehicle_id,
            },
            document=document,
        ) from exc
    except ValidationError as exc:
        raise InputLoadError(
            "Calibrated vehicle profile failed schema validation.",
            input_name="calibration",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


__all__ = [
    "load_and_apply_calibration",
    "load_calibration_profile",
    "write_calibration_profile",
]
