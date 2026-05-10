import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from adapters.envelope import (
    EnvelopeInputs,
    EstimatorResultEnvelope,
    build_estimator_envelope,
    build_internal_error_envelope,
    build_invalid_input_envelope,
    render_envelope_json,
)
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.markdown import render_envelope_markdown
from adapters.terrain_grid import load_terrain_grid
from estimator import EstimateStatus, try_estimate_mission_distance_time
from schemas import MissionPlan, VehicleProfile
from tests.helpers import make_mission_payload, make_vehicle_payload

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden"


def _load_fixture_terrain(
    fixture_dir: Path,
    mission: MissionPlan,
) -> tuple[object | None, InputDocument | None]:
    if mission.assets.terrain_file is None:
        return None, None
    terrain_path = fixture_dir / mission.assets.terrain_file
    terrain_provider, terrain_doc = load_terrain_grid(terrain_path)
    return terrain_provider, terrain_doc


def _render_fixture_envelope(scenario: str) -> str:
    fixture_dir = FIXTURE_ROOT / scenario
    mission, mission_doc = load_mission(fixture_dir / "mission.yaml")
    vehicle, vehicle_doc = load_vehicle(fixture_dir / "vehicle.yaml")
    terrain_provider, terrain_doc = _load_fixture_terrain(fixture_dir, mission)
    result = try_estimate_mission_distance_time(mission, vehicle, terrain_provider=terrain_provider)
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=mission_doc, vehicle=vehicle_doc, terrain=terrain_doc),
    )
    return render_envelope_json(envelope)


def _render_fixture_markdown(scenario: str) -> str:
    fixture_dir = FIXTURE_ROOT / scenario
    mission, mission_doc = load_mission(fixture_dir / "mission.yaml")
    vehicle, vehicle_doc = load_vehicle(fixture_dir / "vehicle.yaml")
    terrain_provider, terrain_doc = _load_fixture_terrain(fixture_dir, mission)
    result = try_estimate_mission_distance_time(mission, vehicle, terrain_provider=terrain_provider)
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=mission_doc, vehicle=vehicle_doc, terrain=terrain_doc),
    )
    return render_envelope_markdown(envelope)


@pytest.mark.parametrize("scenario", ["success", "partial", "infeasible", "terrain"])
def test_canonical_json_matches_golden_fixture(scenario: str) -> None:
    rendered = _render_fixture_envelope(scenario)
    expected = (FIXTURE_ROOT / scenario / "envelope.json").read_text(encoding="utf-8")

    assert rendered == expected


@pytest.mark.parametrize("scenario", ["success", "partial", "infeasible", "terrain"])
def test_markdown_matches_golden_fixture(scenario: str) -> None:
    rendered = _render_fixture_markdown(scenario)
    expected = (FIXTURE_ROOT / scenario / "report.md").read_text(encoding="utf-8")

    assert rendered == expected


def test_mission_schema_rejects_unknown_top_level_fields() -> None:
    payload = make_mission_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        MissionPlan.model_validate(payload)


def test_vehicle_schema_rejects_unknown_top_level_fields() -> None:
    payload = make_vehicle_payload()
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        VehicleProfile.model_validate(payload)


def test_envelope_schema_rejects_unknown_top_level_fields() -> None:
    payload = json.loads(
        (FIXTURE_ROOT / "success" / "envelope.json").read_text(encoding="utf-8")
    )
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        EstimatorResultEnvelope.model_validate(payload)


def test_invalid_input_envelope_uses_stable_parse_context_and_failed_input_provenance(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.json"
    mission_path.write_text("{", encoding="utf-8")

    with pytest.raises(InputLoadError) as exc_info:
        load_mission(mission_path)

    envelope = build_invalid_input_envelope(error=exc_info.value)
    diagnostic = envelope.diagnostics[0]

    assert envelope.status == EstimateStatus.ERROR
    assert diagnostic.message == "Unable to parse mission file."
    assert diagnostic.context["stage"] == "parse"
    assert diagnostic.context["parse_error_type"] == "JSONDecodeError"
    assert "error" not in diagnostic.context
    assert envelope.provenance.inputs["mission"].format == "json"


def test_invalid_input_envelope_uses_stable_schema_validation_context(
    tmp_path: Path,
) -> None:
    payload = make_mission_payload()
    payload["route"][1].pop("lat")
    mission_path = tmp_path / "mission.yaml"
    mission_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InputLoadError) as exc_info:
        load_mission(mission_path)

    envelope = build_invalid_input_envelope(error=exc_info.value)
    diagnostic = envelope.diagnostics[0]

    assert diagnostic.message == "Mission file failed schema validation."
    assert diagnostic.context["stage"] == "schema_validation"
    assert diagnostic.context["validation_error_count"] >= 1
    assert diagnostic.context["first_error_type"] is not None
    assert "error" not in diagnostic.context


def test_internal_error_envelope_uses_stable_error_type_context() -> None:
    envelope = build_internal_error_envelope(error=RuntimeError("boom"))
    diagnostic = envelope.diagnostics[0]

    assert envelope.status == EstimateStatus.ERROR
    assert diagnostic.message == "Unexpected internal error while running estimator CLI."
    assert diagnostic.context == {"error_type": "RuntimeError"}
