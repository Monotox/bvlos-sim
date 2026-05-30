import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from tests.helpers import make_mission_payload, make_vehicle_payload

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
) -> tuple[Path, Path]:
    population_path = tmp_path / "population.yaml"
    _write_yaml(
        population_path,
        {
            "origin_lat": 51.99,
            "origin_lon": 3.99,
            "step_lat_deg": 0.01,
            "step_lon_deg": 0.01,
            "density_ppl_km2": [[density_ppl_km2] * 3 for _ in range(3)],
        },
    )

    mission_payload = make_mission_payload()
    mission_payload["assets"] = {"population_grid_file": population_path.name}
    if airspace is not None:
        mission_payload["airspace"] = airspace
    if sora is not None:
        mission_payload["sora"] = sora

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
        tmp_path, airspace={"class": "G", "max_altitude_agl_m": 120.0}
    )

    result = _invoke(mission_path, vehicle_path, "markdown")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "# SORA Pre-Assessment: pipeline_demo_001" in result.stdout
    assert "SAIL:" in result.stdout
    assert "## Applicable OSOs at SAIL" in result.stdout
    assert "OSO#01" in result.stdout
    assert "not a certified determination" in result.stdout


def test_sora_json_envelope_contains_sail(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path, airspace={"class": "G", "max_altitude_agl_m": 120.0}
    )

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "sora-envelope.v1"
    assert payload["sora_schema_version"] == "sora-assessment.v1"
    assessment = payload["result"]
    assert assessment["intrinsic_grc"] == 3
    assert assessment["final_grc"] == 3
    assert assessment["air_risk_class"] == "b"
    assert assessment["sail"] == "II"
    assert assessment["applicable_osos"]


def test_near_aerodrome_yields_higher_arc_than_low_altitude(tmp_path: Path) -> None:
    low_dir = tmp_path / "low"
    aero_dir = tmp_path / "aero"
    low_dir.mkdir()
    aero_dir.mkdir()

    low_mission, low_vehicle = _write_inputs(
        low_dir, airspace={"class": "G", "max_altitude_agl_m": 120.0}
    )
    aero_mission, aero_vehicle = _write_inputs(
        aero_dir,
        airspace={"class": "G", "max_altitude_agl_m": 120.0, "near_aerodrome": True},
    )

    low = json.loads(_invoke(low_mission, low_vehicle, "json").stdout)["result"]
    aero = json.loads(_invoke(aero_mission, aero_vehicle, "json").stdout)["result"]

    assert low["air_risk_class"] == "b"
    assert aero["air_risk_class"] == "d"


def test_missing_airspace_reports_grc_only(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(tmp_path, airspace=None)

    result = _invoke(mission_path, vehicle_path, "json")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assessment = json.loads(result.stdout)["result"]
    assert assessment["final_grc"] == 3
    assert assessment["air_risk_class"] is None
    assert assessment["sail"] is None
    assert "AIRSPACE_DESCRIPTOR_MISSING" in {
        advisory["code"] for advisory in assessment["advisories"]
    }


def test_grc_above_seven_flags_certified_category(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={"class": "G", "max_altitude_agl_m": 120.0},
        dimension_m=20.0,
        density_ppl_km2=60_000.0,
    )

    assessment = json.loads(_invoke(mission_path, vehicle_path, "json").stdout)["result"]

    assert assessment["final_grc"] > 7
    assert assessment["sail"] == "certified"
    assert assessment["applicable_osos"] == []
    assert "OPERATION_OUTSIDE_SPECIFIC_CATEGORY" in {
        advisory["code"] for advisory in assessment["advisories"]
    }


def test_ground_risk_mitigations_lower_sail(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={"class": "G", "max_altitude_agl_m": 120.0},
        density_ppl_km2=600.0,  # density row -> iGRC 5 for a 1 m vehicle
        sora={
            "ground_risk_mitigations": {
                "m1_strategic": {"applied": True, "robustness": "high"},
            }
        },
    )

    assessment = json.loads(_invoke(mission_path, vehicle_path, "json").stdout)["result"]

    assert assessment["intrinsic_grc"] == 5
    assert assessment["final_grc"] == 3
    assert assessment["intrinsic_sail"] == "IV"
    assert assessment["sail"] == "II"
    assert assessment["sora_version"] == "2.0"
    credits = assessment["ground_risk_mitigations"]
    assert credits == [
        {
            "mitigation_id": "M1",
            "title": "Strategic mitigations for ground risk",
            "robustness": "high",
            "grc_credit": -2,
        }
    ]


def test_tactical_air_risk_mitigation_lowers_arc(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        # above 500 ft AGL in controlled airspace -> ARC-d
        airspace={"class": "C", "max_altitude_agl_m": 300.0},
        sora={"air_risk": {"tactical_mitigation": {"applied": True, "robustness": "high"}}},
    )

    assessment = json.loads(_invoke(mission_path, vehicle_path, "json").stdout)["result"]

    assert assessment["initial_air_risk_class"] == "d"
    assert assessment["air_risk_class"] == "b"
    assert assessment["tactical_air_risk_mitigation"] == {
        "robustness": "high",
        "arc_bands_reduced": 2,
    }


def test_markdown_shows_mitigation_ladder(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={"class": "G", "max_altitude_agl_m": 120.0},
        density_ppl_km2=600.0,
        sora={
            "ground_risk_mitigations": {
                "m1_strategic": {"applied": True, "robustness": "high"},
            }
        },
    )

    result = _invoke(mission_path, vehicle_path, "markdown")

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "## Ground Risk Mitigation Ladder (SORA 2.0)" in result.stdout
    assert "Intrinsic SAIL:" in result.stdout
    assert "Mitigated SAIL:" in result.stdout
    assert "M1 Strategic mitigations for ground risk (high): -2" in result.stdout
    assert "not a certified determination" in result.stdout


def test_unsupported_sora_version_emits_advisory(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={"class": "G", "max_altitude_agl_m": 120.0},
        density_ppl_km2=600.0,
        sora={
            "version": "9.9",
            "ground_risk_mitigations": {
                "m1_strategic": {"applied": True, "robustness": "high"},
            },
        },
    )

    assessment = json.loads(_invoke(mission_path, vehicle_path, "json").stdout)["result"]

    assert assessment["final_grc"] == assessment["intrinsic_grc"]
    assert assessment["ground_risk_mitigations"] == []
    assert "MITIGATION_VERSION_UNSUPPORTED" in {
        advisory["code"] for advisory in assessment["advisories"]
    }


def test_missing_dimension_reports_no_ground_risk(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(
        tmp_path,
        airspace={"class": "G", "max_altitude_agl_m": 120.0},
        dimension_m=None,
    )

    assessment = json.loads(_invoke(mission_path, vehicle_path, "json").stdout)["result"]

    assert assessment["intrinsic_grc"] is None
    assert assessment["final_grc"] is None
    assert assessment["sail"] is None
    assert "GROUND_RISK_NOT_COMPUTED" in {
        advisory["code"] for advisory in assessment["advisories"]
    }
