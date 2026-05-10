"""GeoJSON adapter for static geofence inputs."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from adapters.geojson import GeoJsonEntry
from adapters.geojson import GeoJsonGeometryType
from adapters.geojson import GeoJsonLoadStage
from adapters.geojson import geojson_entries_from_root
from adapters.geojson import polygon_payloads_from_geometry
from adapters.geojson import read_geojson_object
from adapters.io import InputDocument
from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.core.enums import GeofenceKind
from estimator.core.geofence import GeofenceZone
from estimator.core.results import EstimatorContextValue
from estimator.core.results import EstimatorFailure

GeofenceLoadStage = GeoJsonLoadStage

_SUPPORTED_ROOT_GEOMETRIES = {
    GeoJsonGeometryType.POLYGON,
    GeoJsonGeometryType.MULTI_POLYGON,
}


@dataclass(frozen=True)
class GeofenceLoadError(ValueError):
    """Raised when GeoJSON geofence input cannot be loaded."""

    message: str
    path: Path
    stage: GeofenceLoadStage
    failure: EstimatorFailure
    document: InputDocument | None = None

    def __str__(self) -> str:
        return self.message


def load_geofences(path: Path) -> tuple[list[GeofenceZone], InputDocument]:
    """Load static geofence zones from a GeoJSON file."""

    root, document = read_geojson_object(
        path,
        format_error_message="Unsupported geofence file format. Use .geojson or .json.",
        read_error_message="Unable to read geofence file.",
        parse_error_message="Unable to parse geofence GeoJSON file.",
        root_error_message="Geofence GeoJSON root must be an object.",
        error_factory=_invalid_geometry_error,
    )
    entries = geojson_entries_from_root(
        root,
        default_id_prefix="geofence",
        supported_root_geometry_types=_SUPPORTED_ROOT_GEOMETRIES,
        unsupported_root_message="Unsupported GeoJSON geofence root type.",
        path=path,
        document=document,
        invalid_geometry_error=_invalid_geometry_error,
        unsupported_geometry_error=_unsupported_geometry_error,
    )
    zones = [_zone_from_entry(entry, path=path, document=document) for entry in entries]
    return zones, document


def _zone_from_entry(
    entry: GeoJsonEntry,
    *,
    path: Path,
    document: InputDocument,
) -> GeofenceZone:
    kind = _parse_kind(
        entry.properties.get("kind", GeofenceKind.FORBIDDEN),
        entry,
        path=path,
        document=document,
    )
    polygons = polygon_payloads_from_geometry(
        entry.geometry,
        feature_index=entry.index,
        unsupported_message="Unsupported GeoJSON geofence geometry type.",
        path=path,
        document=document,
        invalid_geometry_error=_invalid_geometry_error,
        unsupported_geometry_error=_unsupported_geometry_error,
    )

    try:
        return GeofenceZone.model_validate(
            {
                "id": entry.id,
                "kind": kind,
                "geometry": {"polygons": polygons},
            }
        )
    except ValidationError as exc:
        raise _schema_validation_error(
            exc,
            path=path,
            document=document,
            feature_index=entry.index,
        ) from exc


def _parse_kind(
    value: object,
    entry: GeoJsonEntry,
    *,
    path: Path,
    document: InputDocument,
) -> GeofenceKind:
    try:
        return GeofenceKind(str(value))
    except ValueError as exc:
        raise _invalid_geometry_error(
            "GeoJSON geofence kind must be forbidden or required.",
            path,
            GeofenceLoadStage.FEATURE,
            {"feature_index": entry.index, "kind": str(value)},
            document,
        ) from exc


def _schema_validation_error(
    exc: ValidationError,
    *,
    path: Path,
    document: InputDocument,
    feature_index: int,
) -> GeofenceLoadError:
    first_error = exc.errors(include_url=False)[0]
    return _invalid_geometry_error(
        "GeoJSON geofence geometry failed schema validation.",
        path,
        GeofenceLoadStage.GEOMETRY,
        {
            "feature_index": feature_index,
            "first_error_path": ".".join(str(part) for part in first_error["loc"]),
            "first_error_type": str(first_error["type"]),
        },
        document,
    )


def _invalid_geometry_error(
    message: str,
    path: Path,
    stage: GeofenceLoadStage,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None,
) -> GeofenceLoadError:
    return _error(
        message,
        path=path,
        stage=stage,
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.INVALID_GEOMETRY,
        context=context,
        document=document,
    )


def _unsupported_geometry_error(
    message: str,
    path: Path,
    geometry_type: str,
    feature_index: int | None,
    document: InputDocument | None,
) -> GeofenceLoadError:
    context: dict[str, EstimatorContextValue] = {
        "geometry_type": geometry_type,
        "stage": GeofenceLoadStage.GEOMETRY.value,
    }
    if feature_index is not None:
        context["feature_index"] = feature_index
    return _error(
        message,
        path=path,
        stage=GeofenceLoadStage.GEOMETRY,
        kind=FailureKind.UNSUPPORTED,
        code=FailureCode.UNSUPPORTED_GEOMETRY_TYPE,
        context=context,
        document=document,
    )


def _error(
    message: str,
    *,
    path: Path,
    stage: GeofenceLoadStage,
    kind: FailureKind,
    code: FailureCode,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None = None,
) -> GeofenceLoadError:
    return GeofenceLoadError(
        message=message,
        path=path,
        stage=stage,
        document=document,
        failure=EstimatorFailure(
            kind=kind,
            code=code,
            message=message,
            context={
                "input_name": "geofences",
                "path": str(path),
                "stage": stage.value,
                **context,
            },
        ),
    )
