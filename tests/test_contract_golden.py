import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from adapters.canonical_json import (
    canonical_float,
    canonical_json_value,
    render_canonical_json,
)
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
from adapters.wind_grid import load_wind_grid
from estimator import EstimateStatus, try_estimate_mission_distance_time
from estimator.core.enums import FailureCode, GeofenceKind, WarningCode
from estimator.core.results import (
    EnergyEstimate,
    EstimatorWarning,
    GeofenceConflict,
    GeofenceEstimate,
    LinkEstimate,
    MissionEstimate,
    ResourceEstimate,
    RthReserveTimelinePoint,
)
from schemas import MissionPlan, VehicleProfile
from tests.helpers import make_mission_payload, make_vehicle_payload

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden"


def _build_fixture_envelope(scenario: str) -> EstimatorResultEnvelope:
    fixture_dir = FIXTURE_ROOT / scenario
    mission, mission_doc = load_mission(fixture_dir / "mission.yaml")
    vehicle, vehicle_doc = load_vehicle(fixture_dir / "vehicle.yaml")

    terrain_provider = None
    terrain_doc = None
    if mission.assets.terrain_file is not None:
        terrain_path = fixture_dir / mission.assets.terrain_file
        terrain_provider, terrain_doc = load_terrain_grid(terrain_path)

    wind_provider = None
    wind_grid_doc = None
    if mission.assets.wind_grid_file is not None:
        wind_grid_path = fixture_dir / mission.assets.wind_grid_file
        wind_provider, wind_grid_doc = load_wind_grid(wind_grid_path)

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        terrain_provider=terrain_provider,
        wind_provider=wind_provider,
    )
    return build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(
            mission=mission_doc,
            vehicle=vehicle_doc,
            terrain=terrain_doc,
            wind_grid=wind_grid_doc,
        ),
    )


def _render_fixture_envelope(scenario: str) -> str:
    return render_envelope_json(_build_fixture_envelope(scenario))


def _render_fixture_markdown(scenario: str) -> str:
    return render_envelope_markdown(_build_fixture_envelope(scenario))


@pytest.mark.parametrize(
    "scenario", ["success", "partial", "infeasible", "terrain", "spatiotemporal_wind"]
)
def test_canonical_json_matches_golden_fixture(scenario: str) -> None:
    rendered = _render_fixture_envelope(scenario)
    expected = (FIXTURE_ROOT / scenario / "envelope.json").read_text(encoding="utf-8")

    assert rendered == expected


@pytest.mark.parametrize(
    "scenario", ["success", "partial", "infeasible", "terrain", "spatiotemporal_wind"]
)
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


def test_envelope_schema_rejects_wrong_contract_version() -> None:
    payload = json.loads(
        (FIXTURE_ROOT / "success" / "envelope.json").read_text(encoding="utf-8")
    )
    payload["schema_version"] = "estimator-envelope.v8"

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


def test_invalid_input_envelope_uses_stable_root_type_context(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    mission_path.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(InputLoadError) as exc_info:
        load_mission(mission_path)

    envelope = build_invalid_input_envelope(error=exc_info.value)
    diagnostic = envelope.diagnostics[0]

    assert diagnostic.context["stage"] == "root_type"
    assert diagnostic.context["root_type"] == "list"


def test_internal_error_envelope_uses_stable_error_type_context() -> None:
    envelope = build_internal_error_envelope(error=RuntimeError("boom"))
    diagnostic = envelope.diagnostics[0]

    assert envelope.status == EstimateStatus.ERROR
    assert (
        diagnostic.message == "Unexpected internal error while running estimator CLI."
    )
    assert diagnostic.context == {"error_type": "RuntimeError"}


# ---------------------------------------------------------------------------
# canonical_json utility unit tests
# ---------------------------------------------------------------------------


def test_canonical_float_rejects_inf() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_float(math.inf)


def test_canonical_float_rejects_nan() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_float(math.nan)


def test_canonical_float_normalizes_negative_zero_to_positive() -> None:
    result = canonical_float(-0.0)
    assert result == 0.0
    assert math.copysign(1.0, result) == 1.0


def test_canonical_json_value_recurses_into_nested_list_and_dict() -> None:
    result = canonical_json_value({"vals": [1.23456789012345, None, "text"]})
    assert isinstance(result["vals"][0], float)  # type: ignore[index]
    assert result["vals"][1] is None  # type: ignore[index]
    assert result["vals"][2] == "text"  # type: ignore[index]


def test_render_canonical_json_sorts_keys_and_ends_with_newline() -> None:
    output = render_canonical_json({"z": 1, "a": 2})
    assert output.index('"a"') < output.index('"z"')
    assert output.endswith("\n")


# ---------------------------------------------------------------------------
# Markdown sections: resource, link, geofence feasibility
# ---------------------------------------------------------------------------


def _fake_doc(name: str) -> InputDocument:
    return InputDocument(
        path=Path(f"/fake/{name}.yaml"), format="yaml", sha256="0" * 64
    )


def _bare_mission_estimate(**kwargs) -> MissionEstimate:
    return MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=100.0,
        total_vertical_distance_m=10.0,
        total_path_distance_m=101.0,
        total_time_s=60.0,
        totals_are_partial=False,
        **kwargs,
    )


def _build_minimal_envelope(result: MissionEstimate) -> str:
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(
            mission=_fake_doc("mission"), vehicle=_fake_doc("vehicle")
        ),
    )
    return render_envelope_markdown(envelope)


def test_markdown_includes_resource_feasibility_section_when_present() -> None:
    result = _bare_mission_estimate(
        resource=ResourceEstimate(
            is_feasible=True,
            selected_resource_id="fiber-power",
            total_demand_wh=420.0,
            peak_power_w=2000.0,
            route_distance_m=100.0,
            route_time_s=60.0,
            max_observed_home_distance_m=50.0,
        )
    )
    md = _build_minimal_envelope(result)
    assert "## Resource Feasibility" in md
    assert "fiber-power" in md


def test_markdown_includes_link_feasibility_section_when_present() -> None:
    result = _bare_mission_estimate(
        link=LinkEstimate(
            is_feasible=True,
            selected_link_id="satcom",
            required_link_count=1,
            available_link_count=1,
            max_observed_range_m=5000.0,
        )
    )
    md = _build_minimal_envelope(result)
    assert "## Link Feasibility" in md
    assert "satcom" in md


def test_markdown_includes_geofence_feasibility_section_when_present() -> None:
    result = _bare_mission_estimate(
        geofence=GeofenceEstimate(
            is_feasible=False,
            checked_zone_count=1,
            checked_leg_count=2,
            conflicts=[
                GeofenceConflict(
                    code=FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE,
                    message="route enters forbidden zone",
                    zone_id="EHR06A",
                    zone_kind=GeofenceKind.FORBIDDEN,
                    leg_index=0,
                    route_item_index=0,
                    route_item_id="wp-0",
                )
            ],
        ),
    )
    md = _build_minimal_envelope(result)
    assert "## Geofence Feasibility" in md
    assert "Conflicts: `1`" in md


def test_markdown_includes_rth_reserve_timeline_when_present() -> None:
    result = _bare_mission_estimate(
        energy=EnergyEstimate(
            is_feasible=True,
            total_energy_wh=100.0,
            battery_capacity_wh=900.0,
            usable_energy_wh=675.0,
            reserve_threshold_percent=25.0,
            reserve_threshold_wh=225.0,
            reserve_at_landing_wh=800.0,
            reserve_at_landing_percent=88.88888888888889,
            rth_reserve_timeline=[
                RthReserveTimelinePoint(
                    leg_index=0,
                    route_item_index=0,
                    route_item_id="wp0",
                    rth_distance_m=1200.0,
                    rth_energy_wh=10.0,
                    energy_remaining_before_rth_wh=850.0,
                    reserve_after_rth_wh=840.0,
                    reserve_margin_wh=615.0,
                    is_feasible=True,
                )
            ],
        )
    )

    md = _build_minimal_envelope(result)

    assert "## RTH Reserve Timeline" in md
    assert "| 0 | wp0 |" in md


def test_markdown_warning_without_leg_index_omits_leg_tag() -> None:
    result = _bare_mission_estimate(
        warnings=[
            EstimatorWarning(
                code=WarningCode.GEOFENCE_EVALUATED_2D_ONLY,
                message="altitude bounds not checked",
                leg_index=None,
            )
        ]
    )
    md = _build_minimal_envelope(result)
    assert "## Warnings" in md
    assert "GEOFENCE_EVALUATED_2D_ONLY" in md
    assert "(leg " not in md
