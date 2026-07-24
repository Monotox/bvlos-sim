"""Shared preflight validation engine (Ticket 107).

Builds :class:`FileCheck` results by running the real input/asset loaders and
capturing per-file failures, so a ``--validate-only`` run can validate every
file (including referenced GeoJSON/terrain/population assets) and report each one
instead of aborting on the first failure. Commands assemble a list of file
checks and hand it to :func:`emit_preflight`, which prints either the legacy
plain-text lines or a deterministic ``preflight-validation.v1`` JSON envelope.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import typer
from pydantic import ValidationError

from bvlos_sim.adapters.assets.geofence_geojson import GeofenceLoadError, load_geofences
from bvlos_sim.adapters.assets.landing_zone_geojson import (
    LandingZoneLoadError,
    load_landing_zones,
)
from bvlos_sim.adapters.assets.obstacle_geojson import ObstacleLoadError, load_obstacles
from bvlos_sim.adapters.assets.population_grid import load_population_grid
from bvlos_sim.adapters.assets.terrain_grid import load_terrain_grid
from bvlos_sim.adapters.assets.wind_grid import load_wind_grid
from bvlos_sim.adapters.cli_contract import CliExitCode, PreflightFormat
from bvlos_sim.adapters.io import InputLoadError, InputLoadStage
from bvlos_sim.adapters.preflight_envelope import render_preflight_report
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.preflight_validation import (
    PREFLIGHT_VALIDATION_SCHEMA_VERSION,
    FileCheck,
    PreflightError,
    PreflightValidationReport,
)

_GEOJSON_ASSET_ERRORS = (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError)

# InputLoadStage -> (preflight stage, stable code).
_INPUT_STAGE_MAP: dict[InputLoadStage, tuple[str, str]] = {
    InputLoadStage.SCHEMA_VALIDATION: ("schema", "SCHEMA_VALIDATION_FAILED"),
    InputLoadStage.ROOT_TYPE: ("schema", "ROOT_TYPE_INVALID"),
    InputLoadStage.PARSE: ("asset-load", "PARSE_FAILED"),
    InputLoadStage.READ: ("asset-load", "ASSET_FILE_MISSING"),
    InputLoadStage.FORMAT_DETECTION: ("asset-load", "UNSUPPORTED_FILE_FORMAT"),
}

# GeoJsonLoadStage value -> (preflight stage, stable code). The GeoJSON loaders
# carry their own stage enum whose values match these strings.
_GEOJSON_STAGE_MAP: dict[str, tuple[str, str]] = {
    "read": ("asset-load", "ASSET_FILE_MISSING"),
    "parse": ("asset-load", "GEOJSON_PARSE_FAILED"),
    "format_detection": ("asset-load", "UNSUPPORTED_FILE_FORMAT"),
    "root_type": ("schema", "ROOT_TYPE_INVALID"),
    "schema_validation": ("schema", "SCHEMA_VALIDATION_FAILED"),
    "feature": ("asset-load", "GEOJSON_FEATURE_INVALID"),
    "geometry": ("asset-load", "GEOJSON_GEOMETRY_INVALID"),
}

# Mission asset field -> (role, loader). comms_coverage_file is reserved for a
# later phase and not loaded by any run, so it is not preflight-checked.
_MISSION_ASSET_LOADERS: list[tuple[str, str, Callable[[Path], Any]]] = [
    ("geofences_file", "geofence", load_geofences),
    ("landing_zones_file", "landing-zone", load_landing_zones),
    ("terrain_file", "terrain", load_terrain_grid),
    ("population_grid_file", "population", load_population_grid),
    ("obstacles_file", "obstacle", load_obstacles),
    ("wind_grid_file", "wind-grid", load_wind_grid),
]


def _detail_or_none(detail: dict[str, Any]) -> dict[str, Any] | None:
    cleaned = {key: value for key, value in detail.items() if value is not None}
    return cleaned or None


def _translate(exc: Exception) -> tuple[str, PreflightError]:
    """Map a loader exception onto a (stage, PreflightError) pair."""
    if isinstance(exc, _GEOJSON_ASSET_ERRORS):
        stage, code = _GEOJSON_STAGE_MAP.get(
            str(exc.stage), ("asset-load", "ASSET_LOAD_FAILED")
        )
        detail = dict(exc.failure.context) if exc.failure.context else {}
        detail.setdefault("failure_code", str(exc.failure.code.value))
        return stage, PreflightError(
            code=code, message=str(exc), detail=_detail_or_none(detail)
        )
    if isinstance(exc, InputLoadError):
        stage, code = _INPUT_STAGE_MAP.get(exc.stage, ("schema", "INPUT_LOAD_FAILED"))
        return stage, PreflightError(
            code=code, message=str(exc), detail=_detail_or_none(dict(exc.details))
        )
    if isinstance(exc, ValidationError):
        return "schema", PreflightError(
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            detail={"validation_error_count": len(exc.errors())},
        )
    if isinstance(exc, json.JSONDecodeError):
        return "asset-load", PreflightError(code="PARSE_FAILED", message=str(exc))
    return "schema", PreflightError(code="VALIDATION_FAILED", message=str(exc))


def check_file(
    *,
    role: str,
    path_str: str,
    loader: Callable[[], Any],
) -> tuple[FileCheck, Any | None]:
    """Run ``loader`` and return its ``FileCheck`` plus the loaded value (or None).

    Never raises: a loader failure becomes a failed ``FileCheck`` so callers can
    collect every problem in one pass.
    """
    try:
        result = loader()
    except Exception as exc:  # noqa: BLE001 — every loader failure becomes a FileCheck
        stage, error = _translate(exc)
        return (
            FileCheck(path=path_str, role=role, ok=False, stage=stage, error=error),
            None,
        )
    return FileCheck(path=path_str, role=role, ok=True), result


def mission_asset_checks(
    mission_model: MissionPlan, *, mission_path: Path
) -> list[FileCheck]:
    """Validate every referenced mission asset, one ``FileCheck`` per file."""
    checks: list[FileCheck] = []
    base = mission_path.parent
    for field, role, loader in _MISSION_ASSET_LOADERS:
        relative: Path | None = getattr(mission_model.assets, field)
        if relative is None:
            continue
        resolved = relative if relative.is_absolute() else base / relative
        check, _ = check_file(
            role=role,
            path_str=str(relative),
            loader=lambda res=resolved, fn=loader: fn(res),
        )
        checks.append(check)
    return checks


def build_report(command: str, files: list[FileCheck]) -> PreflightValidationReport:
    return PreflightValidationReport(
        schema_version=PREFLIGHT_VALIDATION_SCHEMA_VERSION,
        command=command,
        ok=all(check.ok for check in files),
        files=files,
    )


def emit_preflight(
    *,
    command: str,
    files: list[FileCheck],
    as_json: bool,
    text_ok_lines: list[str],
) -> NoReturn:
    """Emit the preflight result and exit 0 (all ok) or 11 (any failure).

    In JSON mode a ``preflight-validation.v1`` envelope is written to stdout. In
    text mode the legacy ``role: name: OK`` lines are printed unchanged when every
    file is valid; on failure each failed file is reported to stderr.
    """
    ok = all(check.ok for check in files)
    if as_json:
        typer.echo(render_preflight_report(build_report(command, files)), nl=False)
    elif ok:
        for line in text_ok_lines:
            typer.echo(line)
    else:
        for check in files:
            if check.ok:
                continue
            message = check.error.message if check.error else "validation failed"
            typer.echo(f"{check.role}: {check.path}: FAILED ({message})", err=True)
    code = CliExitCode.SUCCESS if ok else CliExitCode.INVALID_INPUT
    raise typer.Exit(code=int(code))


def is_json_format(validate_format: PreflightFormat) -> bool:
    return validate_format is PreflightFormat.JSON


# Safety-relevant mission blocks that are schema-optional. A file truncated at
# a clean line boundary can silently lose them, so validate-only names their
# absence without failing the check.
_OPTIONAL_SAFETY_BLOCKS = ("constraints", "assets", "policy")


def mission_block_notes(mission: Any) -> list[str]:
    """Advisory notes for safety-relevant blocks the mission never declared."""
    fields_set = getattr(mission, "model_fields_set", frozenset())
    absent = [name for name in _OPTIONAL_SAFETY_BLOCKS if name not in fields_set]
    if not absent:
        return []
    return ["no " + "/".join(absent) + " block declared"]


def format_note_suffix(notes: list[str]) -> str:
    if not notes:
        return ""
    return " (note: " + "; ".join(notes) + ")"


__all__ = [
    "build_report",
    "check_file",
    "emit_preflight",
    "format_note_suffix",
    "is_json_format",
    "mission_asset_checks",
    "mission_block_notes",
]
