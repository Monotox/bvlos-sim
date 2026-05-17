"""Input loading for SITL evidence bundles."""

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
from schemas import SitlEvidenceBundle


def load_sitl_evidence_bundle(path: Path) -> tuple[SitlEvidenceBundle, InputDocument]:
    """Load and validate a SITL evidence bundle from YAML or JSON."""

    parsed, document = read_and_parse_document(path, input_name="sitl_evidence")
    payload = validate_mapping_root(parsed, input_name="sitl_evidence", path=path)
    try:
        return SitlEvidenceBundle.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "SITL evidence file failed schema validation.",
            input_name="sitl_evidence",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


__all__ = ["load_sitl_evidence_bundle"]
