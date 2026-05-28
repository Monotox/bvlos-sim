"""YAML/JSON population-grid.v1 population density adapter."""

from pathlib import Path
from typing import Any

from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
)
from estimator.environment.population import GridPopulationProvider


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
        return GridPopulationProvider(
            origin_lat=float(payload["origin_lat"]),
            origin_lon=float(payload["origin_lon"]),
            step_lat_deg=float(payload["step_lat_deg"]),
            step_lon_deg=float(payload["step_lon_deg"]),
            density_ppl_km2=[
                [float(value) for value in row]
                for row in payload["density_ppl_km2"]
            ],
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


__all__ = ["PopulationGridLoadError", "load_population_grid"]
