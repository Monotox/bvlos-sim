"""GeoJSON adapter for static obstacle inputs."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from adapters.assets.geojson import (
    GeoJsonEntry,
    GeoJsonGeometryType,
    GeoJsonLoadStage,
    geojson_entries_from_root,
    polygon_payload_from_coordinates,
    position_payload_from_coordinates,
    read_geojson_object,
)
from adapters.io import InputDocument, validation_error_summary
from estimator.core.enums import FailureCode, FailureKind
from estimator.core.obstacle import Obstacle
from estimator.core.results import EstimatorContextValue, EstimatorFailure
from estimator.environment.obstacle import ListObstacleProvider

ObstacleLoadStage = GeoJsonLoadStage

_SUPPORTED_ROOT_GEOMETRIES = {
    GeoJsonGeometryType.POINT,
    GeoJsonGeometryType.LINE_STRING,
    GeoJsonGeometryType.POLYGON,
}


@dataclass(frozen=True)
class ObstacleLoadError(ValueError):
    """Raised when GeoJSON obstacle input cannot be loaded."""

    message: str
    path: Path
    stage: ObstacleLoadStage
    failure: EstimatorFailure
    document: InputDocument | None = None

    def __str__(self) -> str:
        return self.message


GeometryPayloadBuilder = Callable[
    [GeoJsonEntry, Path, InputDocument],
    dict[str, Any],
]


def load_obstacles(path: Path) -> tuple[ListObstacleProvider, InputDocument]:
    """Load static obstacle features from a GeoJSON file."""

    root, document = read_geojson_object(
        path,
        format_error_message="Unsupported obstacle file format. Use .geojson or .json.",
        read_error_message="Unable to read obstacle file.",
        parse_error_message="Unable to parse obstacle GeoJSON file.",
        root_error_message="Obstacle GeoJSON root must be an object.",
        error_factory=_invalid_geometry_error,
    )
    entries = geojson_entries_from_root(
        root,
        default_id_prefix="obstacle",
        supported_root_geometry_types=_SUPPORTED_ROOT_GEOMETRIES,
        unsupported_root_message="Unsupported GeoJSON obstacle root type.",
        path=path,
        document=document,
        invalid_geometry_error=_invalid_geometry_error,
        unsupported_geometry_error=_unsupported_geometry_error,
    )
    obstacles = [
        _obstacle_from_entry(entry, path=path, document=document) for entry in entries
    ]
    return ListObstacleProvider(obstacles), document


def _obstacle_from_entry(
    entry: GeoJsonEntry,
    *,
    path: Path,
    document: InputDocument,
) -> Obstacle:
    try:
        payload = {
            "id": entry.id,
            "geometry": _geometry_payload(entry, path, document),
            "height_m": _required_float_property(
                entry,
                "height_m",
                path=path,
                document=document,
            ),
            "radius_m": _optional_float_property(
                entry,
                "radius_m",
                default=0.0,
                path=path,
                document=document,
            ),
            "uncertainty_m": _optional_float_property(
                entry,
                "uncertainty_m",
                default=0.0,
                path=path,
                document=document,
            ),
            "metadata": entry.properties,
        }
        return Obstacle.model_validate(payload)
    except ValidationError as exc:
        raise _schema_validation_error(
            exc,
            path=path,
            document=document,
            feature_index=entry.index,
        ) from exc


def _geometry_payload(
    entry: GeoJsonEntry,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    builders: dict[str, GeometryPayloadBuilder] = {
        GeoJsonGeometryType.POINT.value: _point_payload,
        GeoJsonGeometryType.LINE_STRING.value: _line_payload,
        GeoJsonGeometryType.POLYGON.value: _polygon_payload,
    }
    geometry_type = str(entry.geometry.get("type"))
    builder = builders.get(geometry_type)
    if builder is not None:
        return builder(entry, path, document)

    raise _unsupported_geometry_error(
        "Unsupported GeoJSON obstacle geometry type.",
        path,
        geometry_type,
        entry.index,
        document,
    )


def _point_payload(
    entry: GeoJsonEntry,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    return {
        "type": "point",
        "points": [
            position_payload_from_coordinates(
                entry.geometry.get("coordinates"),
                feature_index=entry.index,
                ring_index=None,
                position_index=0,
                path=path,
                document=document,
                invalid_geometry_error=_invalid_geometry_error,
            )
        ],
    }


def _line_payload(
    entry: GeoJsonEntry,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    coordinates = entry.geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise _invalid_geometry_error(
            "GeoJSON LineString.coordinates must contain at least two positions.",
            path,
            ObstacleLoadStage.GEOMETRY,
            {"feature_index": entry.index},
            document,
        )
    return {
        "type": "line",
        "points": [
            position_payload_from_coordinates(
                position,
                feature_index=entry.index,
                ring_index=None,
                position_index=position_index,
                path=path,
                document=document,
                invalid_geometry_error=_invalid_geometry_error,
            )
            for position_index, position in enumerate(coordinates)
        ],
    }


def _polygon_payload(
    entry: GeoJsonEntry,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    polygon = polygon_payload_from_coordinates(
        entry.geometry.get("coordinates"),
        feature_index=entry.index,
        path=path,
        document=document,
        invalid_geometry_error=_invalid_geometry_error,
    )
    return {
        "type": "polygon",
        "polygon": {"exterior": polygon["exterior"]},
    }


def _required_float_property(
    entry: GeoJsonEntry,
    name: str,
    *,
    path: Path,
    document: InputDocument,
) -> float:
    if name not in entry.properties:
        raise _invalid_geometry_error(
            f"GeoJSON obstacle feature must define properties.{name}.",
            path,
            ObstacleLoadStage.FEATURE,
            {"feature_index": entry.index, "property": name},
            document,
        )
    return _float_property_value(entry, name, path=path, document=document)


def _optional_float_property(
    entry: GeoJsonEntry,
    name: str,
    *,
    default: float,
    path: Path,
    document: InputDocument,
) -> float:
    if name not in entry.properties:
        return default
    return _float_property_value(entry, name, path=path, document=document)


def _float_property_value(
    entry: GeoJsonEntry,
    name: str,
    *,
    path: Path,
    document: InputDocument,
) -> float:
    value = entry.properties.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid_geometry_error(
            f"GeoJSON obstacle properties.{name} must be numeric.",
            path,
            ObstacleLoadStage.FEATURE,
            {
                "feature_index": entry.index,
                "property": name,
                "value_type": type(value).__name__,
            },
            document,
        )
    return float(value)


def _schema_validation_error(
    exc: ValidationError,
    *,
    path: Path,
    document: InputDocument,
    feature_index: int,
) -> ObstacleLoadError:
    return _invalid_geometry_error(
        "GeoJSON obstacle geometry failed schema validation.",
        path,
        ObstacleLoadStage.GEOMETRY,
        {"feature_index": feature_index, **validation_error_summary(exc)},
        document,
    )


def _invalid_geometry_error(
    message: str,
    path: Path,
    stage: ObstacleLoadStage,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None,
) -> ObstacleLoadError:
    code = (
        FailureCode.ASSET_LOAD_ERROR
        if stage == ObstacleLoadStage.READ
        else FailureCode.INVALID_GEOMETRY
    )
    return _error(
        message,
        path=path,
        stage=stage,
        kind=FailureKind.INVALID_INPUT,
        code=code,
        context=context,
        document=document,
    )


def _unsupported_geometry_error(
    message: str,
    path: Path,
    geometry_type: str,
    feature_index: int | None,
    document: InputDocument | None,
) -> ObstacleLoadError:
    context: dict[str, EstimatorContextValue] = {
        "geometry_type": geometry_type,
        "stage": ObstacleLoadStage.GEOMETRY.value,
    }
    if feature_index is not None:
        context["feature_index"] = feature_index
    return _error(
        message,
        path=path,
        stage=ObstacleLoadStage.GEOMETRY,
        kind=FailureKind.UNSUPPORTED,
        code=FailureCode.UNSUPPORTED_GEOMETRY_TYPE,
        context=context,
        document=document,
    )


def _error(
    message: str,
    *,
    path: Path,
    stage: ObstacleLoadStage,
    kind: FailureKind,
    code: FailureCode,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None = None,
) -> ObstacleLoadError:
    return ObstacleLoadError(
        message=message,
        path=path,
        stage=stage,
        document=document,
        failure=EstimatorFailure(
            kind=kind,
            code=code,
            message=message,
            context={
                "input_name": "obstacles",
                "path": str(path),
                "stage": stage.value,
                **context,
            },
        ),
    )


__all__ = ["ObstacleLoadError", "load_obstacles"]
