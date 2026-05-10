"""YAML/JSON spatiotemporal wind grid adapter."""

from pathlib import Path
from typing import Any

from adapters.io import (
    InputDocument,
    InputLoadError,
    InputLoadStage,
    read_and_parse_document,
)
from estimator.environment.wind import SpatiotemporalWindProvider


class WindGridLoadError(InputLoadError):
    """Raised when a spatiotemporal wind grid file cannot be loaded."""


def load_wind_grid(path: Path) -> tuple[SpatiotemporalWindProvider, InputDocument]:
    """Load a SpatiotemporalWindProvider from a YAML or JSON wind grid file."""
    parsed, document = read_and_parse_document(path, input_name="wind_grid")
    if not isinstance(parsed, dict):
        raise WindGridLoadError(
            "Wind grid file must contain a mapping/object at the root.",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.ROOT_TYPE,
            document=document,
        )
    return _build_provider(parsed, path=path, document=document), document


def _require_monotonic(axis: list[float], name: str, *, path: Path, document: InputDocument) -> None:
    if len(axis) < 2:
        raise WindGridLoadError(
            f"Wind grid axis '{name}' must have at least 2 entries; got {len(axis)}.",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        )
    if not all(axis[i] < axis[i + 1] for i in range(len(axis) - 1)):
        raise WindGridLoadError(
            f"Wind grid axis '{name}' must be strictly monotonically increasing.",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        )


def _validate_values_shape(
    values: Any,
    *,
    n_t: int,
    n_a: int,
    n_lat: int,
    n_lon: int,
    path: Path,
    document: InputDocument,
) -> None:
    def _fail(detail: str) -> None:
        raise WindGridLoadError(
            f"Wind grid 'values' shape must be [n_time={n_t}][n_alt={n_a}][n_lat={n_lat}][n_lon={n_lon}] "
            f"with each innermost element [east_mps, north_mps]. {detail}",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        )
    if not isinstance(values, list) or len(values) != n_t:
        _fail(f"Outer (time) length is {len(values) if isinstance(values, list) else type(values).__name__}, expected {n_t}.")
    for t_idx, a_block in enumerate(values):
        if not isinstance(a_block, list) or len(a_block) != n_a:
            _fail(f"values[{t_idx}] length is {len(a_block) if isinstance(a_block, list) else '?'}, expected {n_a}.")
        for a_idx, lat_block in enumerate(a_block):
            if not isinstance(lat_block, list) or len(lat_block) != n_lat:
                _fail(f"values[{t_idx}][{a_idx}] length expected {n_lat}.")
            for lat_idx, lon_block in enumerate(lat_block):
                if not isinstance(lon_block, list) or len(lon_block) != n_lon:
                    _fail(f"values[{t_idx}][{a_idx}][{lat_idx}] length expected {n_lon}.")
                for lon_idx, en in enumerate(lon_block):
                    if not isinstance(en, list) or len(en) != 2:
                        _fail(f"values[{t_idx}][{a_idx}][{lat_idx}][{lon_idx}] must be [east, north].")


def _build_provider(
    payload: dict[str, Any],
    *,
    path: Path,
    document: InputDocument,
) -> SpatiotemporalWindProvider:
    try:
        axes = payload["axes"]
        time_s = [float(v) for v in axes["time_s"]]
        altitude_m = [float(v) for v in axes["altitude_m"]]
        lat = [float(v) for v in axes["lat"]]
        lon = [float(v) for v in axes["lon"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise WindGridLoadError(
            f"Wind grid file is missing required axes fields or has invalid values: {exc}",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        ) from exc

    for name, axis in [("time_s", time_s), ("altitude_m", altitude_m), ("lat", lat), ("lon", lon)]:
        _require_monotonic(axis, name, path=path, document=document)

    try:
        values = payload["values"]
    except KeyError as exc:
        raise WindGridLoadError(
            "Wind grid file is missing required field 'values'.",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        ) from exc

    _validate_values_shape(
        values,
        n_t=len(time_s),
        n_a=len(altitude_m),
        n_lat=len(lat),
        n_lon=len(lon),
        path=path,
        document=document,
    )

    try:
        return SpatiotemporalWindProvider(
            time_s=time_s,
            altitude_m=altitude_m,
            lat=lat,
            lon=lon,
            values=values,
        )
    except (TypeError, ValueError) as exc:
        raise WindGridLoadError(
            f"Wind grid values contain invalid numeric data: {exc}",
            input_name="wind_grid",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            document=document,
        ) from exc
