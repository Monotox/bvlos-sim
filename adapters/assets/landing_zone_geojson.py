"""GeoJSON adapter for static landing-zone inputs."""

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
    polygon_payloads_from_geometry,
    position_payload_from_coordinates,
    read_geojson_object,
)
from adapters.io import InputDocument, validation_error_summary
from estimator.core.enums import FailureCode, FailureKind
from estimator.core.landing_zone import LandingZone
from estimator.core.results import EstimatorContextValue, EstimatorFailure

LandingZoneLoadStage = GeoJsonLoadStage

_SUPPORTED_ROOT_GEOMETRIES = {
    GeoJsonGeometryType.POINT,
    GeoJsonGeometryType.POLYGON,
    GeoJsonGeometryType.MULTI_POLYGON,
}


@dataclass(frozen=True)
class LandingZoneLoadError(ValueError):
    """Raised when GeoJSON landing-zone input cannot be loaded."""

    message: str
    path: Path
    stage: LandingZoneLoadStage
    failure: EstimatorFailure
    document: InputDocument | None = None

    def __str__(self) -> str:
        return self.message


GeometryPayloadBuilder = Callable[
    [dict[str, Any], int, Path, InputDocument],
    dict[str, Any],
]


def load_landing_zones(path: Path) -> tuple[list[LandingZone], InputDocument]:
    """Load static landing zones from a GeoJSON file."""

    root, document = read_geojson_object(
        path,
        format_error_message=(
            "Unsupported landing-zone file format. Use .geojson or .json."
        ),
        read_error_message="Unable to read landing-zone file.",
        parse_error_message="Unable to parse landing-zone GeoJSON file.",
        root_error_message="Landing-zone GeoJSON root must be an object.",
        error_factory=_invalid_geometry_error,
    )
    entries = geojson_entries_from_root(
        root,
        default_id_prefix="landing-zone",
        supported_root_geometry_types=_SUPPORTED_ROOT_GEOMETRIES,
        unsupported_root_message="Unsupported GeoJSON landing-zone root type.",
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
) -> LandingZone:
    try:
        return LandingZone.model_validate(
            {
                "id": entry.id,
                "geometry": _geometry_payload(
                    entry.geometry,
                    feature_index=entry.index,
                    path=path,
                    document=document,
                ),
                "metadata": entry.properties,
            }
        )
    except ValidationError as exc:
        raise _schema_validation_error(
            exc,
            path=path,
            document=document,
            feature_index=entry.index,
        ) from exc


def _geometry_payload(
    geometry: dict[str, Any],
    *,
    feature_index: int,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    builders: dict[str, GeometryPayloadBuilder] = {
        GeoJsonGeometryType.POINT.value: _point_payload,
        GeoJsonGeometryType.POLYGON.value: _polygon_payload,
        GeoJsonGeometryType.MULTI_POLYGON.value: _polygon_payload,
    }
    geometry_type = str(geometry.get("type"))
    builder = builders.get(geometry_type)
    if builder is not None:
        return builder(geometry, feature_index, path, document)

    raise _unsupported_geometry_error(
        "Unsupported GeoJSON landing-zone geometry type.",
        path,
        geometry_type,
        feature_index,
        document,
    )


def _point_payload(
    geometry: dict[str, Any],
    feature_index: int,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    return {
        "points": [
            position_payload_from_coordinates(
                geometry.get("coordinates"),
                feature_index=feature_index,
                ring_index=None,
                position_index=0,
                path=path,
                document=document,
                invalid_geometry_error=_invalid_geometry_error,
            )
        ]
    }


def _polygon_payload(
    geometry: dict[str, Any],
    feature_index: int,
    path: Path,
    document: InputDocument,
) -> dict[str, Any]:
    return {
        "polygons": polygon_payloads_from_geometry(
            geometry,
            feature_index=feature_index,
            unsupported_message="Unsupported GeoJSON landing-zone geometry type.",
            path=path,
            document=document,
            invalid_geometry_error=_invalid_geometry_error,
            unsupported_geometry_error=_unsupported_geometry_error,
        )
    }


def _schema_validation_error(
    exc: ValidationError,
    *,
    path: Path,
    document: InputDocument,
    feature_index: int,
) -> LandingZoneLoadError:
    return _invalid_geometry_error(
        "GeoJSON landing-zone geometry failed schema validation.",
        path,
        LandingZoneLoadStage.GEOMETRY,
        {"feature_index": feature_index, **validation_error_summary(exc)},
        document,
    )


def _invalid_geometry_error(
    message: str,
    path: Path,
    stage: LandingZoneLoadStage,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None,
) -> LandingZoneLoadError:
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
) -> LandingZoneLoadError:
    context: dict[str, EstimatorContextValue] = {
        "geometry_type": geometry_type,
        "stage": LandingZoneLoadStage.GEOMETRY.value,
    }
    if feature_index is not None:
        context["feature_index"] = feature_index
    return _error(
        message,
        path=path,
        stage=LandingZoneLoadStage.GEOMETRY,
        kind=FailureKind.UNSUPPORTED,
        code=FailureCode.UNSUPPORTED_LANDING_ZONE_GEOMETRY,
        context=context,
        document=document,
    )


def _error(
    message: str,
    *,
    path: Path,
    stage: LandingZoneLoadStage,
    kind: FailureKind,
    code: FailureCode,
    context: dict[str, EstimatorContextValue],
    document: InputDocument | None = None,
) -> LandingZoneLoadError:
    return LandingZoneLoadError(
        message=message,
        path=path,
        stage=stage,
        document=document,
        failure=EstimatorFailure(
            kind=kind,
            code=code,
            message=message,
            context={
                "input_name": "landing_zones",
                "path": str(path),
                "stage": stage.value,
                **context,
            },
        ),
    )
