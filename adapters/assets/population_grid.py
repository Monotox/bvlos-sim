"""YAML/JSON diagnostic and SORA ``population-grid.v2`` adapter."""

from datetime import datetime
import math
from pathlib import Path
from typing import Any

from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
)
from estimator.environment.population import GridPopulationProvider, PopulationEvidence


class PopulationGridLoadError(InputLoadError):
    """Raised when a population-density grid file cannot be loaded."""


def load_population_grid(path: Path) -> tuple[GridPopulationProvider, InputDocument]:
    """Load a GridPopulationProvider from a YAML or JSON population grid file."""
    parsed, document = read_and_parse_document(path, input_name="population")
    if not isinstance(parsed, dict):
        raise PopulationGridLoadError(
            "Population file must contain a mapping/object at the root.",
            input_name="population",
            path=path,
            stage=InputLoadStage.ROOT_TYPE,
            document=document,
        )
    return _build_provider(parsed, path=path, document=document), document


def _build_provider(
    payload: dict[str, Any],
    *,
    path: Path,
    document: InputDocument,
) -> GridPopulationProvider:
    try:
        evidence = _population_evidence(payload)
        return GridPopulationProvider(
            origin_lat=_finite_number(payload["origin_lat"], "origin_lat"),
            origin_lon=_finite_number(payload["origin_lon"], "origin_lon"),
            step_lat_deg=_finite_number(payload["step_lat_deg"], "step_lat_deg"),
            step_lon_deg=_finite_number(payload["step_lon_deg"], "step_lon_deg"),
            density_ppl_km2=[
                [
                    _finite_number(value, f"density_ppl_km2[{row_index}][{col_index}]")
                    for col_index, value in enumerate(row)
                ]
                for row_index, row in enumerate(payload["density_ppl_km2"])
            ],
            sora_evidence=evidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PopulationGridLoadError(
            "Population grid file is missing required fields or has invalid "
            f"values: {exc}",
            input_name="population",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        ) from exc


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a numeric value, not a boolean or string")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _nonblank_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonblank string")
    return value.strip()


def _datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        instant = value
    else:
        text = _nonblank_string(value, field)
        try:
            instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return instant


def _population_evidence(payload: dict[str, Any]) -> PopulationEvidence | None:
    schema_version = payload.get("schema_version")
    if schema_version is None:
        return None
    if schema_version != "population-grid.v2":
        raise ValueError(
            f"unsupported population grid schema_version {schema_version!r}"
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("population-grid.v2 metadata must be a mapping")
    value_semantics = _nonblank_string(
        metadata.get("value_semantics"), "metadata.value_semantics"
    )
    if value_semantics != "conservative_cell_maximum":
        raise ValueError("metadata.value_semantics must be 'conservative_cell_maximum'")
    year = metadata.get("population_year")
    if isinstance(year, bool) or not isinstance(year, int) or year < 1900:
        raise ValueError("metadata.population_year must be an integer >= 1900")
    assemblies = metadata.get("operational_footprint_assemblies_present")
    if not isinstance(assemblies, bool):
        raise ValueError(
            "metadata.operational_footprint_assemblies_present must be a boolean"
        )
    valid_from = _datetime(metadata.get("valid_from"), "metadata.valid_from")
    valid_until = _datetime(metadata.get("valid_until"), "metadata.valid_until")
    if valid_until <= valid_from:
        raise ValueError("metadata.valid_until must be later than valid_from")
    native_resolution_m = _finite_number(
        metadata.get("native_resolution_m"), "metadata.native_resolution_m"
    )
    effective_resolution_m = _finite_number(
        metadata.get("effective_resolution_m"), "metadata.effective_resolution_m"
    )
    if native_resolution_m <= 0.0 or effective_resolution_m <= 0.0:
        raise ValueError("population evidence resolutions must be positive")
    return PopulationEvidence(
        source=_nonblank_string(metadata.get("source"), "metadata.source"),
        population_year=year,
        native_resolution_m=native_resolution_m,
        effective_resolution_m=effective_resolution_m,
        authority_assessment_reference=_nonblank_string(
            metadata.get("authority_assessment_reference"),
            "metadata.authority_assessment_reference",
        ),
        valid_from=valid_from,
        valid_until=valid_until,
        transient_population_assessment_reference=_nonblank_string(
            metadata.get("transient_population_assessment_reference"),
            "metadata.transient_population_assessment_reference",
        ),
        operational_footprint_assemblies_present=assemblies,
        value_semantics=value_semantics,
    )


__all__ = ["PopulationGridLoadError", "load_population_grid"]
