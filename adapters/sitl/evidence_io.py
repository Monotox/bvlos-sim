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
from schemas import SitlArtifactReference, SitlEvidenceBundle, SitlObservedArtifacts


def _resolved_reference(
    reference: SitlArtifactReference,
    *,
    evidence_dir: Path,
) -> SitlArtifactReference:
    reference_path = Path(reference.path)
    if reference_path.is_absolute() or ":" in reference.path.split("/", maxsplit=1)[0]:
        return reference
    return reference.model_copy(
        update={"path": str((evidence_dir / reference_path).resolve(strict=False))}
    )


def _resolve_bundle_references(
    bundle: SitlEvidenceBundle,
    *,
    evidence_dir: Path,
) -> SitlEvidenceBundle:
    def resolve(reference: SitlArtifactReference) -> SitlArtifactReference:
        return _resolved_reference(reference, evidence_dir=evidence_dir)

    expected = bundle.expected.model_copy(
        update={
            "reports": [resolve(reference) for reference in bundle.expected.reports]
        }
    )
    observed = SitlObservedArtifacts(
        telemetry=[resolve(reference) for reference in bundle.observed.telemetry],
        command_logs=[resolve(reference) for reference in bundle.observed.command_logs],
        simulator_logs=[
            resolve(reference) for reference in bundle.observed.simulator_logs
        ],
        adapter_logs=[resolve(reference) for reference in bundle.observed.adapter_logs],
    )
    return bundle.model_copy(
        update={
            "inputs": [resolve(reference) for reference in bundle.inputs],
            "expected": expected,
            "observed": observed,
        }
    )


def load_sitl_evidence_bundle(path: Path) -> tuple[SitlEvidenceBundle, InputDocument]:
    """Load and validate a SITL evidence bundle from YAML or JSON."""

    parsed, document = read_and_parse_document(path, input_name="sitl_evidence")
    payload = validate_mapping_root(parsed, input_name="sitl_evidence", path=path)
    try:
        bundle = SitlEvidenceBundle.model_validate(payload)
        return (
            _resolve_bundle_references(
                bundle,
                evidence_dir=document.path.resolve(strict=False).parent,
            ),
            document,
        )
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
