"""YAML loading adapter for diagnostic uncertainty plans (uncertainty.v2)."""

from pathlib import Path

from pydantic import ValidationError

from bvlos_sim.adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from bvlos_sim.schemas.uncertainty import UncertaintyPlan


def resolve_uncertainty_asset_path(relative: str, *, uncertainty_path: Path) -> Path:
    """Resolve a path relative to the uncertainty file's directory."""
    p = Path(relative)
    if p.is_absolute():
        return p
    return uncertainty_path.parent / p


def load_uncertainty_plan(path: Path) -> tuple[UncertaintyPlan, InputDocument]:
    """Load and validate an uncertainty plan from a YAML or JSON file."""
    parsed, document = read_and_parse_document(path, input_name="uncertainty")
    payload = validate_mapping_root(parsed, input_name="uncertainty", path=path)
    try:
        return UncertaintyPlan.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Uncertainty file failed schema validation.",
            input_name="uncertainty",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc
