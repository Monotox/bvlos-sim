"""Shared GeoJSON parsing helpers for static feature adapters."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from adapters.io import InputDocument
from estimator.core.results import EstimatorContextValue


class GeoJsonLoadStage(StrEnum):
    FORMAT_DETECTION = "format_detection"
    READ = "read"
    PARSE = "parse"
    ROOT_TYPE = "root_type"
    FEATURE = "feature"
    GEOMETRY = "geometry"


class GeoJsonGeometryType(StrEnum):
    FEATURE_COLLECTION = "FeatureCollection"
    FEATURE = "Feature"
    POINT = "Point"
    POLYGON = "Polygon"
    MULTI_POLYGON = "MultiPolygon"


@dataclass(frozen=True)
class GeoJsonEntry:
    """A root geometry or feature geometry normalized for domain adapters."""

    id: str
    index: int
    properties: dict[str, Any]
    geometry: dict[str, Any]


GeoJsonErrorFactory = Callable[
    [
        str,
        Path,
        GeoJsonLoadStage,
        dict[str, EstimatorContextValue],
        InputDocument | None,
    ],
    Exception,
]
UnsupportedGeometryErrorFactory = Callable[
    [str, Path, str, int | None, InputDocument | None],
    Exception,
]


def read_geojson_object(
    path: Path,
    *,
    format_error_message: str,
    read_error_message: str,
    parse_error_message: str,
    root_error_message: str,
    error_factory: GeoJsonErrorFactory,
) -> tuple[dict[str, Any], InputDocument]:
    """Read a GeoJSON file and return an object root plus provenance."""

    _detect_geojson_format(
        path,
        message=format_error_message,
        error_factory=error_factory,
    )
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise error_factory(
            read_error_message,
            path,
            GeoJsonLoadStage.READ,
            {"read_error_type": type(exc).__name__},
            None,
        ) from exc

    document = InputDocument(
        path=path,
        format="geojson",
        sha256=sha256(raw_bytes).hexdigest(),
    )
    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise error_factory(
            parse_error_message,
            path,
            GeoJsonLoadStage.PARSE,
            {"parse_error_type": type(exc).__name__},
            document,
        ) from exc

    if isinstance(parsed, dict):
        return parsed, document
    raise error_factory(
        root_error_message,
        path,
        GeoJsonLoadStage.ROOT_TYPE,
        {"root_type": type(parsed).__name__},
        document,
    )


def geojson_entries_from_root(
    root: dict[str, Any],
    *,
    default_id_prefix: str,
    supported_root_geometry_types: set[GeoJsonGeometryType],
    unsupported_root_message: str,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
    unsupported_geometry_error: UnsupportedGeometryErrorFactory,
) -> list[GeoJsonEntry]:
    """Normalize a FeatureCollection, Feature, or supported root geometry."""

    root_type = root.get("type")
    if root_type == GeoJsonGeometryType.FEATURE_COLLECTION:
        features = _require_feature_list(
            root.get("features"),
            path=path,
            document=document,
            invalid_geometry_error=invalid_geometry_error,
            context={"geojson_type": root_type},
        )
        return [
            _entry_from_feature(
                feature,
                index,
                default_id_prefix=default_id_prefix,
                path=path,
                document=document,
                invalid_geometry_error=invalid_geometry_error,
            )
            for index, feature in enumerate(features)
        ]

    if root_type == GeoJsonGeometryType.FEATURE:
        return [
            _entry_from_feature(
                root,
                0,
                default_id_prefix=default_id_prefix,
                path=path,
                document=document,
                invalid_geometry_error=invalid_geometry_error,
            )
        ]

    if root_type in supported_root_geometry_types:
        return [
            GeoJsonEntry(
                id=f"{default_id_prefix}-0",
                index=0,
                properties={},
                geometry=root,
            )
        ]

    raise unsupported_geometry_error(
        unsupported_root_message,
        path,
        str(root_type),
        None,
        document,
    )


def polygon_payloads_from_geometry(
    geometry: dict[str, Any],
    *,
    feature_index: int,
    unsupported_message: str,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
    unsupported_geometry_error: UnsupportedGeometryErrorFactory,
) -> list[dict[str, Any]]:
    """Return domain-model polygon payloads from Polygon or MultiPolygon geometry."""

    geometry_type = str(geometry.get("type"))
    coordinates = geometry.get("coordinates")
    builders = {
        GeoJsonGeometryType.POLYGON.value: lambda: [
            polygon_payload_from_coordinates(
                coordinates,
                feature_index=feature_index,
                path=path,
                document=document,
                invalid_geometry_error=invalid_geometry_error,
            )
        ],
        GeoJsonGeometryType.MULTI_POLYGON.value: lambda: _multipolygon_payloads(
            coordinates,
            feature_index=feature_index,
            path=path,
            document=document,
            invalid_geometry_error=invalid_geometry_error,
        ),
    }
    builder = builders.get(geometry_type)
    if builder is not None:
        return builder()

    raise unsupported_geometry_error(
        unsupported_message,
        path,
        geometry_type,
        feature_index,
        document,
    )


def polygon_payload_from_coordinates(
    value: Any,
    *,
    feature_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> dict[str, Any]:
    if not isinstance(value, list) or not value:
        raise invalid_geometry_error(
            "GeoJSON Polygon.coordinates must contain at least one ring.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {"feature_index": feature_index},
            document,
        )
    return {
        "exterior": ring_payload_from_coordinates(
            value[0],
            feature_index=feature_index,
            ring_index=0,
            path=path,
            document=document,
            invalid_geometry_error=invalid_geometry_error,
        ),
        "holes": [
            ring_payload_from_coordinates(
                ring,
                feature_index=feature_index,
                ring_index=ring_index,
                path=path,
                document=document,
                invalid_geometry_error=invalid_geometry_error,
            )
            for ring_index, ring in enumerate(value[1:], start=1)
        ],
    }


def position_payload_from_coordinates(
    value: Any,
    *,
    feature_index: int,
    ring_index: int | None,
    position_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> dict[str, float]:
    if not isinstance(value, list | tuple) or len(value) < 2:
        raise invalid_geometry_error(
            "GeoJSON positions must be arrays of at least [lon, lat].",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {
                "feature_index": feature_index,
                "ring_index": ring_index,
                "position_index": position_index,
            },
            document,
        )

    lon = _parse_position_number(
        value[0],
        field_name="lon",
        feature_index=feature_index,
        ring_index=ring_index,
        position_index=position_index,
        path=path,
        document=document,
        invalid_geometry_error=invalid_geometry_error,
    )
    lat = _parse_position_number(
        value[1],
        field_name="lat",
        feature_index=feature_index,
        ring_index=ring_index,
        position_index=position_index,
        path=path,
        document=document,
        invalid_geometry_error=invalid_geometry_error,
    )
    _validate_lon_lat(
        lon=lon,
        lat=lat,
        feature_index=feature_index,
        ring_index=ring_index,
        position_index=position_index,
        path=path,
        document=document,
        invalid_geometry_error=invalid_geometry_error,
    )
    return {"lat": lat, "lon": lon}


def _detect_geojson_format(
    path: Path,
    *,
    message: str,
    error_factory: GeoJsonErrorFactory,
) -> None:
    suffix = path.suffix.lower()
    if suffix in {".geojson", ".json"}:
        return
    raise error_factory(
        message,
        path,
        GeoJsonLoadStage.FORMAT_DETECTION,
        {"suffix": suffix or None},
        None,
    )


def _require_feature_list(
    value: Any,
    *,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
    context: dict[str, EstimatorContextValue],
) -> list[Any]:
    if isinstance(value, list):
        return value
    raise invalid_geometry_error(
        "GeoJSON FeatureCollection.features must be an array.",
        path,
        GeoJsonLoadStage.FEATURE,
        context,
        document,
    )


def _entry_from_feature(
    feature: Any,
    index: int,
    *,
    default_id_prefix: str,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> GeoJsonEntry:
    if not isinstance(feature, dict):
        raise invalid_geometry_error(
            "GeoJSON features must be objects.",
            path,
            GeoJsonLoadStage.FEATURE,
            {"feature_index": index, "feature_type": type(feature).__name__},
            document,
        )
    if feature.get("type") != GeoJsonGeometryType.FEATURE:
        raise invalid_geometry_error(
            "GeoJSON feature.type must be Feature.",
            path,
            GeoJsonLoadStage.FEATURE,
            {"feature_index": index, "geojson_type": str(feature.get("type"))},
            document,
        )

    properties = _feature_properties(
        feature,
        index=index,
        path=path,
        document=document,
        invalid_geometry_error=invalid_geometry_error,
    )
    geometry = _feature_geometry(
        feature,
        index=index,
        path=path,
        document=document,
        invalid_geometry_error=invalid_geometry_error,
    )
    return GeoJsonEntry(
        id=str(
            feature.get("id") or properties.get("id") or f"{default_id_prefix}-{index}"
        ),
        index=index,
        properties=properties,
        geometry=geometry,
    )


def _feature_properties(
    feature: dict[str, Any],
    *,
    index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    if isinstance(properties, dict):
        return properties
    raise invalid_geometry_error(
        "GeoJSON feature.properties must be an object when present.",
        path,
        GeoJsonLoadStage.FEATURE,
        {"feature_index": index},
        document,
    )


def _feature_geometry(
    feature: dict[str, Any],
    *,
    index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> dict[str, Any]:
    geometry = feature.get("geometry")
    if isinstance(geometry, dict):
        return geometry
    raise invalid_geometry_error(
        "GeoJSON feature.geometry must be an object.",
        path,
        GeoJsonLoadStage.GEOMETRY,
        {"feature_index": index},
        document,
    )


def _multipolygon_payloads(
    value: Any,
    *,
    feature_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise invalid_geometry_error(
            "GeoJSON MultiPolygon.coordinates must be an array.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {
                "feature_index": feature_index,
                "geojson_type": GeoJsonGeometryType.MULTI_POLYGON.value,
            },
            document,
        )
    return [
        polygon_payload_from_coordinates(
            polygon,
            feature_index=feature_index,
            path=path,
            document=document,
            invalid_geometry_error=invalid_geometry_error,
        )
        for polygon in value
    ]


def ring_payload_from_coordinates(
    value: Any,
    *,
    feature_index: int,
    ring_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> list[dict[str, float]]:
    if not isinstance(value, list):
        raise invalid_geometry_error(
            "GeoJSON Polygon ring must be an array.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {"feature_index": feature_index, "ring_index": ring_index},
            document,
        )
    if len(value) < 4:
        raise invalid_geometry_error(
            "GeoJSON Polygon ring must contain at least four positions.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {"feature_index": feature_index, "ring_index": ring_index},
            document,
        )

    ring = [
        position_payload_from_coordinates(
            position,
            feature_index=feature_index,
            ring_index=ring_index,
            position_index=position_index,
            path=path,
            document=document,
            invalid_geometry_error=invalid_geometry_error,
        )
        for position_index, position in enumerate(value)
    ]
    if ring[0] == ring[-1]:
        return ring
    raise invalid_geometry_error(
        "GeoJSON Polygon rings must be closed.",
        path,
        GeoJsonLoadStage.GEOMETRY,
        {"feature_index": feature_index, "ring_index": ring_index},
        document,
    )


def _parse_position_number(
    value: Any,
    *,
    field_name: str,
    feature_index: int,
    ring_index: int | None,
    position_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise invalid_geometry_error(
            "GeoJSON position values must be numbers.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {
                "coordinate": field_name,
                "feature_index": feature_index,
                "ring_index": ring_index,
                "position_index": position_index,
                "value_type": type(value).__name__,
            },
            document,
        )
    return float(value)


def _validate_lon_lat(
    *,
    lon: float,
    lat: float,
    feature_index: int,
    ring_index: int | None,
    position_index: int,
    path: Path,
    document: InputDocument,
    invalid_geometry_error: GeoJsonErrorFactory,
) -> None:
    coordinate_context: dict[str, EstimatorContextValue] = {
        "feature_index": feature_index,
        "ring_index": ring_index,
        "position_index": position_index,
        "coordinate_order": "geojson_lon_lat",
    }
    if not -180 <= lon <= 180:
        raise invalid_geometry_error(
            "GeoJSON longitude must be between -180 and 180.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {**coordinate_context, "lon": lon},
            document,
        )
    if not -90 <= lat <= 90:
        raise invalid_geometry_error(
            "GeoJSON latitude must be between -90 and 90.",
            path,
            GeoJsonLoadStage.GEOMETRY,
            {**coordinate_context, "lat": lat},
            document,
        )
