"""YAML/JSON input loading adapters for CLI surfaces."""

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from estimator.core.results import EstimatorContextValue
from schemas import MissionPlan, VehicleProfile
from schemas.mission import MISSION_SCHEMA_VERSION


@dataclass(frozen=True)
class InputDocument:
    path: Path
    format: str
    sha256: str


class InputLoadStage(StrEnum):
    FORMAT_DETECTION = "format_detection"
    READ = "read"
    PARSE = "parse"
    ROOT_TYPE = "root_type"
    SCHEMA_VALIDATION = "schema_validation"


class InputLoadError(ValueError):
    """Raised when an input file cannot be parsed or validated."""

    def __init__(
        self,
        message: str,
        *,
        input_name: str,
        path: Path,
        stage: InputLoadStage,
        details: dict[str, EstimatorContextValue] | None = None,
        document: InputDocument | None = None,
    ) -> None:
        super().__init__(message)
        self.input_name = input_name
        self.path = path
        self.stage = stage
        self.details = details or {}
        self.document = document

    def to_context(self) -> dict[str, EstimatorContextValue]:
        return {
            "input_name": self.input_name,
            "path": str(self.path),
            "stage": self.stage.value,
            **self.details,
        }


def validation_error_summary(
    exc: ValidationError,
) -> dict[str, EstimatorContextValue]:
    errors = exc.errors(include_url=False)
    first_error = errors[0] if errors else None
    first_error_path = None
    first_error_type = None
    first_error_message = None
    if first_error is not None:
        first_error_path = ".".join(str(part) for part in first_error["loc"])
        first_error_type = str(first_error["type"])
        first_error_message = first_error.get("msg")

    return {
        "validation_error_count": len(errors),
        "first_error_path": first_error_path or None,
        "first_error_type": first_error_type,
        "first_error_message": first_error_message,
    }


def _detect_format(path: Path, *, input_name: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    raise InputLoadError(
        "Unsupported input file format. Use .json, .yaml, or .yml.",
        input_name=input_name,
        path=path,
        stage=InputLoadStage.FORMAT_DETECTION,
        details={"suffix": suffix or None},
    )


def read_and_parse_document(
    path: Path, *, input_name: str
) -> tuple[Any, InputDocument]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise InputLoadError(
            f"Unable to read {input_name} file.",
            input_name=input_name,
            path=path,
            stage=InputLoadStage.READ,
            details={"read_error_type": type(exc).__name__},
        ) from exc

    format_name = _detect_format(path, input_name=input_name)
    document = InputDocument(
        path=path,
        format=format_name,
        sha256=sha256(raw_bytes).hexdigest(),
    )

    try:
        if format_name == "json":
            return json.loads(raw_bytes.decode("utf-8")), document
        return yaml.safe_load(raw_bytes.decode("utf-8")), document
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise InputLoadError(
            f"Unable to parse {input_name} file.",
            input_name=input_name,
            path=path,
            stage=InputLoadStage.PARSE,
            details={
                "format": format_name,
                "parse_error_type": type(exc).__name__,
            },
            document=document,
        ) from exc


def validate_mapping_root(value: Any, *, input_name: str, path: Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise InputLoadError(
        f"{input_name.capitalize()} file must contain a mapping/object at the root.",
        input_name=input_name,
        path=path,
        stage=InputLoadStage.ROOT_TYPE,
        details={"root_type": type(value).__name__},
    )


def load_mission(path: Path) -> tuple[MissionPlan, InputDocument]:
    parsed, document = read_and_parse_document(path, input_name="mission")
    payload = validate_mapping_root(parsed, input_name="mission", path=path)
    if "schema_version" not in payload:
        raise InputLoadError(
            "Mission file must declare schema_version; run 'bvlos-sim migrate' "
            "for legacy mission inputs.",
            input_name="mission",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details={
                "expected_schema_version": MISSION_SCHEMA_VERSION,
                "first_error_path": "schema_version",
                "first_error_type": "missing",
            },
            document=document,
        )
    try:
        return MissionPlan.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Mission file failed schema validation.",
            input_name="mission",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc


def load_vehicle(path: Path) -> tuple[VehicleProfile, InputDocument]:
    parsed, document = read_and_parse_document(path, input_name="vehicle")
    payload = validate_mapping_root(parsed, input_name="vehicle", path=path)
    try:
        return VehicleProfile.model_validate(payload), document
    except ValidationError as exc:
        raise InputLoadError(
            "Vehicle file failed schema validation.",
            input_name="vehicle",
            path=path,
            stage=InputLoadStage.SCHEMA_VALIDATION,
            details=validation_error_summary(exc),
            document=document,
        ) from exc
