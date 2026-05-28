"""YAML/JSON spatiotemporal wind grid adapter."""

from pathlib import Path
from typing import Any, NoReturn

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


def _require_monotonic(
    axis: list[float], name: str, *, path: Path, document: InputDocument
) -> None:
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


def _schema_error(msg: str, *, path: Path, document: InputDocument) -> NoReturn:
    raise WindGridLoadError(
        msg,
        input_name="wind_grid",
        path=path,
        stage=InputLoadStage.SCHEMA_VALIDATION,
        document=document,
    )


def _require_list_of(
    value: object, expected: int, label: str, *, path: Path, document: InputDocument
) -> list[object]:
    if not isinstance(value, list):
        _schema_error(
            f"Wind grid values{label}: expected a list of {expected} elements, got {type(value).__name__}.",
            path=path,
            document=document,
        )
    if len(value) != expected:
        _schema_error(
            f"Wind grid values{label}: expected {expected} elements, got {len(value)}.",
            path=path,
            document=document,
        )
    return value


def _validate_en_pair(
    value: object, label: str, *, path: Path, document: InputDocument
) -> None:
    _require_list_of(value, 2, label, path=path, document=document)


def _validate_lon_row(
    row: object, n_lon: int, label: str, *, path: Path, document: InputDocument
) -> None:
    pairs = _require_list_of(row, n_lon, label, path=path, document=document)
    for i, en in enumerate(pairs):
        _validate_en_pair(en, f"{label}[{i}]", path=path, document=document)


def _validate_lat_block(
    block: object,
    n_lat: int,
    n_lon: int,
    label: str,
    *,
    path: Path,
    document: InputDocument,
) -> None:
    rows = _require_list_of(block, n_lat, label, path=path, document=document)
    for i, row in enumerate(rows):
        _validate_lon_row(row, n_lon, f"{label}[{i}]", path=path, document=document)


def _validate_alt_block(
    block: object,
    n_a: int,
    n_lat: int,
    n_lon: int,
    label: str,
    *,
    path: Path,
    document: InputDocument,
) -> None:
    lat_blocks = _require_list_of(block, n_a, label, path=path, document=document)
    for i, lat_block in enumerate(lat_blocks):
        _validate_lat_block(
            lat_block, n_lat, n_lon, f"{label}[{i}]", path=path, document=document
        )


def _validate_values_shape(
    values: object,
    *,
    n_t: int,
    n_a: int,
    n_lat: int,
    n_lon: int,
    path: Path,
    document: InputDocument,
) -> None:
    time_blocks = _require_list_of(values, n_t, "", path=path, document=document)
    for i, alt_block in enumerate(time_blocks):
        _validate_alt_block(
            alt_block, n_a, n_lat, n_lon, f"[{i}]", path=path, document=document
        )


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

    for name, axis in [
        ("time_s", time_s),
        ("altitude_m", altitude_m),
        ("lat", lat),
        ("lon", lon),
    ]:
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
