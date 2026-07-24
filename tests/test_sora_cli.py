import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from estimator import (
    EstimationOptions,
    LegPhase,
    estimate_mission_distance_time,
)
from estimator.execution.sora import _conservative_route_max_agl_m
from schemas.mission import MissionAction, RouteItem
from tests.helpers import make_mission, make_mission_payload, make_vehicle, make_vehicle_payload

_RUNNER = CliRunner()


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_inputs(
    tmp_path: Path,
    *,
    airspace: dict | None,
    dimension_m: float | None = 1.0,
    density_ppl_km2: float = 12.0,
    sora: dict | None = None,
    include_footprint: bool = True,
    operational_footprint_assemblies_present: bool = False,
) -> tuple[Path, Path]:
    population_path = tmp_path / "population.yaml"
    _write_yaml(
        population_path,
        {
            "schema_version": "population-grid.v2",
            "origin_lat": 51.98,
            "origin_lon": 3.98,
            "step_lat_deg": 0.01,
            "step_lon_deg": 0.01,
            "density_ppl_km2": [[density_ppl_km2] * 5 for _ in range(5)],
            "metadata": {
                "source": "Test conservative population assessment",
                "population_year": 2026,
                "native_resolution_m": 100.0,
                "effective_resolution_m": 100.0,
                "value_semantics": "conservative_cell_maximum",
                "authority_assessment_reference": "TEST-POP-001",
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2026-12-31T23:59:59Z",
                "transient_population_assessment_reference": "TEST-EVENT-001",
                "operational_footprint_assemblies_present": (
                    operational_footprint_assemblies_present
                ),
            },
        },
    )

    terrain_path = tmp_path / "terrain.yaml"
    _write_yaml(
        terrain_path,
        {
            "origin_lat": 51.98,
            "origin_lon": 3.98,
            "step_lat_deg": 0.01,
            "step_lon_deg": 0.01,
            "elevations_m": [[12.0] * 5 for _ in range(5)],
        },
    )

    mission_payload = make_mission_payload()
    mission_payload["departure_time"] = "2026-07-21T12:00:00Z"
    mission_payload["assets"] = {
        "population_grid_file": population_path.name,
        "terrain_file": terrain_path.name,
    }
    if airspace is not None:
        airspace = dict(airspace)
        airspace.setdefault(
            "operational_and_contingency_volume_assessment_reference",
            "Test whole-volume airspace assessment",
        )
        airspace.setdefault("worst_case_arc_declared", True)
        airspace.setdefault("aerodrome_environment", False)
        airspace.setdefault("transponder_mandatory_zone", False)
        mission_payload["airspace"] = airspace
    sora_payload = dict(sora or {})
    if include_footprint:
        sora_payload["ground_risk_footprint"] = {
            "operational_volume_margin_m": 30.0,
            "ground_risk_buffer_m": 300.0,
            "vertical_contingency_margin_m": 10.0,
            "maximum_height_agl_m": 130.0,
            "derivation": "Test fixture conservative 1:1 buffer",
        }
        sora_payload.setdefault(
            "containment_evidence",
            {
                "assessment_reference": "TEST-CONTAINMENT-001",
                "average_population_density_ppl_km2": density_ppl_km2,
                "largest_outdoor_assembly": "below_40000",
                "sheltering_applicable": dimension_m is None or dimension_m <= 3.0,
                "ground_risk_buffer_revalidation_reference": "TEST-GRC-RECHECK-001",
            },
        )
    if sora_payload:
        mission_payload["sora"] = sora_payload

    vehicle_payload = make_vehicle_payload()
    if dimension_m is not None:
        vehicle_payload["characteristic_dimension_m"] = dimension_m

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, vehicle_payload)
    return mission_path, vehicle_path


def _invoke(mission_path: Path, vehicle_path: Path, fmt: str):
    return _RUNNER.invoke(
        app,
        ["sora", str(mission_path), str(vehicle_path), "--format", fmt],
    )


def test_sora_markdown_reports_sail_osos_and_disclaimer(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )

    result = _invoke(mission_path, vehicle_path, "markdown")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "# SORA Pre-Assessment: pipeline_demo_001" in result.stdout
    assert "SAIL:" in result.stdout
    assert "TMPR required robustness:" in result.stdout
    assert "## Table 14 OSOs at SAIL" in result.stdout
    assert "OSO#01" in result.stdout
    assert result.stdout.count("| OSO#") == 17
    assert "| OSO#02 |" in result.stdout
    assert "| NR | no |" in result.stdout
    assert "INCOMPLETE SORA" in result.stdout
    assert "Annex E containment compliance:     NOT ASSESSED" in result.stdout
    assert "not a certified determination" in result.stdout


def test_sora_json_envelope_contains_sail(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "sora-envelope.v3"
    assert payload["sora_schema_version"] == "sora-assessment.v3"
    assessment = payload["result"]
    assert assessment["intrinsic_grc"] == 3
    assert assessment["final_grc"] == 3
    assert assessment["air_risk_class"] == "b"
    assert assessment["sora_version"] == "2.5"
    assert assessment["complete_sora_assessment"] is False
    assert assessment["oso_compliance_status"] == "not_assessed"
    assert assessment["within_specific_category_method_scope"] is True
    assert assessment["max_speed_mps"] == 25.0
    assert (
        assessment["operational_and_contingency_volume_assessment_reference"]
        == "Test whole-volume airspace assessment"
    )
    assert assessment["worst_case_arc_declared"] is True
    assert assessment["population_evidence"]["schema_version"] == "population-grid.v2"
    assert "rural area" in assessment["air_risk_rationale"]
    assert assessment["ground_risk_footprint"] == {
        "buffer_method": "initial_1_to_1",
        "derivation": "Test fixture conservative 1:1 buffer",
        "ground_risk_buffer_m": 300.0,
        "maximum_height_agl_m": 130.0,
        "operational_volume_margin_m": 30.0,
        "vertical_contingency_margin_m": 10.0,
    }
    assert assessment["ground_risk_mitigations"] == []
    assert assessment["tactical_mitigation_requirement"] == {
        "required_robustness": "low"
    }
    assert assessment["sail"] == "II"
    assert assessment["containment_requirement"] == {
        "method": "tables_8_to_13",
        "adjacent_area_outer_limit_m": 5000.0,
        "adjacent_area_assessment_required": True,
        "selected_table": 9,
        "assessment_reference": "TEST-CONTAINMENT-001",
        "average_population_density_ppl_km2": 12.0,
        "largest_outdoor_assembly": "below_40000",
        "sheltering_assumed": True,
        "population_density_operational_limit": "below_5000_ppl_km2",
        "outdoor_assembly_operational_limit": "below_40000",
        "required_robustness": "low",
        "ground_risk_buffer_revalidation_reference": "TEST-GRC-RECHECK-001",
        "within_specific_category_method_scope": True,
        "annex_e_compliance_status": "not_assessed",
    }
    assert len(assessment["applicable_osos"]) == 17
    oso02 = next(
        oso for oso in assessment["applicable_osos"] if oso["oso_id"] == "OSO#02"
    )
    assert oso02["robustness"] == "NR"
    assert oso02["required"] is False
    assert oso02["party_dependencies"]["designer"] == {
        "applicable": True,
        "criterion_refs": [],
    }
    oso05 = next(
        oso for oso in assessment["applicable_osos"] if oso["oso_id"] == "OSO#05"
    )
    assert oso05["note_refs"] == ["4.9.3(c)"]


def test_aerodrome_environment_yields_higher_arc_than_low_altitude(
    tmp_path: Path,
) -> None:
    low_dir = tmp_path / "low"
    aero_dir = tmp_path / "aero"
    low_dir.mkdir()
    aero_dir.mkdir()

    low_mission, low_vehicle = _write_inputs(
        low_dir,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )
    aero_mission, aero_vehicle = _write_inputs(
        aero_dir,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "aerodrome_environment": True,
        },
    )

    low = json.loads(_invoke(low_mission, low_vehicle, "json").stdout)["result"]
    aero = json.loads(_invoke(aero_mission, aero_vehicle, "json").stdout)["result"]

    assert low["air_risk_class"] == "b"
    assert aero["air_risk_class"] == "c"


def test_missing_airspace_is_rejected(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(tmp_path, airspace=None)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "Airspace descriptor is required" in result.stdout


def test_missing_assessed_ground_footprint_is_rejected(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        include_footprint=False,
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "centerline-only population output is diagnostic" in result.stdout


def test_conservative_ground_risk_buffer_must_cover_operational_height(
    tmp_path: Path,
) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        sora={
            "ground_risk_footprint": {
                "operational_volume_margin_m": 30.0,
                "ground_risk_buffer_m": 50.0,
                "vertical_contingency_margin_m": 10.0,
                "maximum_height_agl_m": 130.0,
                "derivation": "Deliberately undersized test fixture",
            }
        },
        include_footprint=False,
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "must be at least the terrain-checked maximum_height_agl_m" in result.stdout


def test_airspace_ceiling_must_cover_verified_maximum_height(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 1.0,
            "over_urban_area": False,
        },
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "must cover the terrain-checked" in result.stdout


def test_grc_above_seven_flags_certified_category(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        dimension_m=20.0,
        density_ppl_km2=600.0,
    )

    result = _invoke(mission_path, vehicle_path, "json")
    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assessment = json.loads(result.stdout)["result"]

    assert assessment["final_grc"] > 7
    assert assessment["sail"] is None
    assert assessment["category_outcome"] == "certified"
    assert assessment["applicable_osos"] == []
    assert "OPERATION_OUTSIDE_SPECIFIC_CATEGORY" in {
        advisory["code"] for advisory in assessment["advisories"]
    }


def test_ground_risk_mitigation_credit_is_rejected_but_reported(
    tmp_path: Path,
) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        density_ppl_km2=600.0,  # density row -> iGRC 5 for a 1 m vehicle
        sora={
            "ground_risk_mitigations": {
                "m1a_sheltering": {
                    "applied": True,
                    "robustness": "medium",
                    "evidence": "Test sheltering dossier",
                },
            }
        },
    )

    result = _invoke(mission_path, vehicle_path, "json")

    # The only problem is the applied mitigation declaration: the assessment
    # is still written without credit, and the exit code is INFEASIBLE (10).
    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assessment = json.loads(result.stdout)["result"]
    assert assessment["intrinsic_grc"] == 5
    assert assessment["final_grc"] == 5
    assert assessment["within_specific_category_method_scope"] is True
    assert assessment["ground_risk_mitigations"] == [
        {
            "mitigation_id": "M1(A)",
            "title": "Strategic mitigation by sheltering",
            "robustness": "medium",
            "evidence": "Test sheltering dossier",
            "nominal_grc_credit": 0,
            "grc_credit": 0,
            "credit_status": "credit_rejected_pending_annex_b",
        }
    ]
    advisory = next(
        advisory
        for advisory in assessment["advisories"]
        if advisory["code"] == "GROUND_MITIGATION_CREDIT_REJECTED"
    )
    assert "Annex B integrity-and-assurance criteria evaluator" in advisory["message"]
    assert "free-text evidence reference cannot earn GRC credit" in advisory["message"]


def test_tactical_air_risk_credit_is_rejected(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        # above 500 ft AGL in controlled airspace -> ARC-d
        airspace={"class": "C", "max_altitude_agl_m": 300.0},
        sora={
            "air_risk": {
                "tactical_mitigation": {
                    "applied": True,
                    "robustness": "high",
                    "evidence": "Test DAA dossier",
                }
            }
        },
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "Mission file failed schema validation" in result.stdout


def test_markdown_request_cannot_bypass_mitigation_credit_gate(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        density_ppl_km2=600.0,
        sora={
            "ground_risk_mitigations": {
                "m1a_sheltering": {
                    "applied": True,
                    "robustness": "medium",
                    "evidence": "Test sheltering dossier",
                },
            }
        },
    )

    result = _invoke(mission_path, vehicle_path, "markdown")

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "## Declared Ground Risk Mitigations: NO CREDIT APPLIED" in result.stdout
    assert "REJECTED pending an Annex B" in result.stdout
    assert "assume NO mitigation credit" in result.stdout
    assert "credit_rejected_pending_annex_b" in result.stdout
    assert "(declared mitigation credit rejected)" in result.stdout
    assert "Annex B integrity-and-assurance criteria evaluator" in result.stdout


def test_unsupported_sora_version_is_rejected(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        density_ppl_km2=600.0,
        sora={
            "version": "9.9",
        },
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "Mission file failed schema validation" in result.stdout


def test_missing_dimension_is_rejected_for_sora(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        dimension_m=None,
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "Ground Risk Class was not computed" in result.stdout


def test_sora_rejects_diagnostic_population_grid(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )
    population_path = tmp_path / "population.yaml"
    population = yaml.safe_load(population_path.read_text(encoding="utf-8"))
    population.pop("schema_version")
    _write_yaml(population_path, population)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "requires a population-grid.v2 asset" in result.stdout


def test_sora_rejects_expired_population_evidence(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )
    population_path = tmp_path / "population.yaml"
    population = yaml.safe_load(population_path.read_text(encoding="utf-8"))
    population["metadata"]["valid_until"] = "2026-06-01T00:00:00Z"
    _write_yaml(population_path, population)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "outside the population evidence validity interval" in result.stdout


def test_sora_rejects_declared_height_below_resolved_route_plus_margin(
    tmp_path: Path,
) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )
    mission = yaml.safe_load(mission_path.read_text(encoding="utf-8"))
    mission["sora"]["ground_risk_footprint"]["maximum_height_agl_m"] = 125.0
    _write_yaml(mission_path, mission)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "route maximum AGL plus vertical_contingency_margin_m" in result.stdout


def test_sora_preserves_estimator_infeasibility_reason(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
    )
    vehicle = yaml.safe_load(vehicle_path.read_text(encoding="utf-8"))
    vehicle["energy"]["battery_capacity_wh"] = 1.0
    _write_yaml(vehicle_path, vehicle)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "INSUFFICIENT_ENERGY" in result.stdout
    assert "Ground Risk Class was not computed" not in result.stdout


def test_operational_footprint_assembly_forces_highest_population_band(
    tmp_path: Path,
) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={
            "class": "G",
            "max_altitude_agl_m": 130.0,
            "over_urban_area": False,
        },
        density_ppl_km2=12.0,
        operational_footprint_assemblies_present=True,
    )

    result = _invoke(mission_path, vehicle_path, "json")
    assessment = json.loads(result.stdout)["result"]

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert assessment["intrinsic_grc"] == 7
    assert (
        assessment["population_evidence"]["operational_footprint_assemblies_present"]
        is True
    )


# ---------------------------------------------------------------------------
# Route AGL verification: stored path coordinate order
# ---------------------------------------------------------------------------


class _RecordingTerrainProvider:
    """Records every segment the AGL check asks about, as (lat, lon) pairs."""

    provider_id = "recording"

    def __init__(self) -> None:
        self.queried: list[tuple[float, float]] = []

    def elevation_at(self, lat: float, lon: float) -> float | None:
        return 0.0

    def conservative_max_elevation_along_segment(
        self, start_lat, start_lon, end_lat, end_lon, *, geod
    ):
        return 0.0

    def conservative_min_elevation_along_segment(
        self, start_lat, start_lon, end_lat, end_lon, *, geod
    ):
        self.queried.append((start_lat, start_lon))
        self.queried.append((end_lat, end_lon))
        return 0.0


def _turning_mission():
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.route = [
        RouteItem(
            id="north",
            action=MissionAction.WAYPOINT,
            lat=52.05,
            lon=4.0,
            altitude_m=120.0,
        ),
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=52.05,
            lon=4.08,
            altitude_m=120.0,
        ),
    ]
    return mission


@pytest.mark.parametrize("fidelity", ["v1", "v2"])
def test_route_agl_check_never_transposes_stored_path_coordinates(
    fidelity: str,
) -> None:
    """Materialized turn arcs store (lon, lat); the AGL walk must not swap them.

    Unpacking them as (lat, lon) sent every turn-arc query to lat 4.0, lon 52.05
    - a different continent - so the check either aborted on a narrow terrain
    grid or verified height over the wrong ground.
    """

    estimate = estimate_mission_distance_time(
        _turning_mission(),
        make_vehicle(),
        options=EstimationOptions(fidelity=fidelity),
    )
    provider = _RecordingTerrainProvider()

    _conservative_route_max_agl_m(estimate, terrain_provider=provider)

    assert provider.queried
    for lat, lon in provider.queried:
        assert 51.9 <= lat <= 52.2, f"latitude {lat} is not on the mission route"
        assert 3.9 <= lon <= 4.2, f"longitude {lon} is not on the mission route"


def test_route_agl_check_covers_materialized_turn_arcs() -> None:
    """The v2 arc must contribute more sampled segments than the v1 corner."""

    v1 = estimate_mission_distance_time(
        _turning_mission(), make_vehicle(), options=EstimationOptions(fidelity="v1")
    )
    v2 = estimate_mission_distance_time(
        _turning_mission(), make_vehicle(), options=EstimationOptions(fidelity="v2")
    )
    v1_provider = _RecordingTerrainProvider()
    v2_provider = _RecordingTerrainProvider()

    _conservative_route_max_agl_m(v1, terrain_provider=v1_provider)
    _conservative_route_max_agl_m(v2, terrain_provider=v2_provider)

    assert any(leg.phase == LegPhase.TURN_ARC for leg in v2.legs)
    assert len(v2_provider.queried) > len(v1_provider.queried)


def test_sora_markdown_carries_provenance(tmp_path: Path) -> None:
    """The filed artifact must say what produced it and what it was proven on.

    render_sora_markdown discarded everything but .result, so the report named
    neither the tool version, the SORA edition, the population vintage, nor the
    input digests, and the terrain that gates the AGL check was absent from
    provenance entirely.
    """

    repo = Path(__file__).resolve().parents[1]
    result = _RUNNER.invoke(
        app,
        [
            "sora",
            str(repo / "examples/missions/pipeline_demo_001_ground_risk.yaml"),
            str(repo / "examples/vehicles/quadplane_v1_ground_risk.yaml"),
            "--format",
            "markdown",
        ],
    )

    out = result.stdout
    assert "## Provenance" in out
    assert "Tool version:" in out
    assert "SORA version:" in out
    assert "Population year:" in out
    assert "Input `terrain`:" in out
    assert "Input `population`:" in out
