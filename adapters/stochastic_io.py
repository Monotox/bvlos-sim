"""YAML loading adapter for diagnostic propagation plans (stochastic.v2)."""

from pathlib import Path

from pydantic import ValidationError

from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
    validate_mapping_root,
    validation_error_summary,
)
from schemas.stochastic import StochasticPropagationPlan


def resolve_stochastic_asset_path(relative: str, *, stochastic_path: Path) -> Path:
    """Resolve a path relative to the stochastic file's directory."""
    p = Path(relative)
    if p.is_absolute():
        return p
    return stochastic_path.parent / p


def load_stochastic_plan(
    path: Path,
) -> tuple[StochasticPropagationPlan, InputDocument]:
    """Load and validate a stochastic propagation plan from YAML or JSON."""
    parsed, document = read_and_parse_document(path, input_name="stochastic")
    payload = validate_mapping_root(parsed, input_name="stochastic", path=path)
    try:
        return StochasticPropagationPlan.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Stochastic file failed schema validation.",
            input_name="stochastic",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc
