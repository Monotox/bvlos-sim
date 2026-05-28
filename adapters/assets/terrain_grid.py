"""YAML/JSON uniform elevation grid terrain adapter."""

from pathlib import Path
from typing import Any

from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
)
from estimator.environment.terrain import GridTerrainProvider


class TerrainGridLoadError(InputLoadError):
    """Raised when an elevation grid file cannot be loaded."""


def load_terrain_grid(path: Path) -> tuple[GridTerrainProvider, InputDocument]:
    """Load a GridTerrainProvider from a YAML or JSON elevation grid file."""
    parsed, document = read_and_parse_document(path, input_name="terrain")
    if not isinstance(parsed, dict):
        raise TerrainGridLoadError(
            "Terrain file must contain a mapping/object at the root.",
            input_name="terrain",
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
) -> GridTerrainProvider:
    try:
        return GridTerrainProvider(
            origin_lat=float(payload["origin_lat"]),
            origin_lon=float(payload["origin_lon"]),
            step_lat_deg=float(payload["step_lat_deg"]),
            step_lon_deg=float(payload["step_lon_deg"]),
            elevations_m=[[float(v) for v in row] for row in payload["elevations_m"]],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TerrainGridLoadError(
            f"Terrain grid file is missing required fields or has invalid values: {exc}",
            input_name="terrain",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        ) from exc
