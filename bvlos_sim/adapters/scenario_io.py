"""YAML/JSON input loading adapter for scenario files."""

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
from bvlos_sim.schemas.scenario import ScenarioPlan


def load_scenario(path: Path) -> tuple[ScenarioPlan, InputDocument]:
    """Load and validate a scenario file from YAML or JSON.

    Raises InputLoadError for all load and validation failures.
    """
    parsed, document = read_and_parse_document(path, input_name="scenario")
    payload = validate_mapping_root(parsed, input_name="scenario", path=path)
    try:
        return ScenarioPlan.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Scenario file failed schema validation.",
            input_name="scenario",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


def resolve_scenario_asset_path(path: Path, *, scenario_path: Path) -> Path:
    """Resolve a path relative to the scenario file directory.

    Absolute paths are returned unchanged.
    """
    if path.is_absolute():
        return path
    return scenario_path.parent / path
