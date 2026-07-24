from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.io import load_mission
from bvlos_sim.adapters.migration import MISSION_V6, migrate_mission_v6_to_v7
from bvlos_sim.schemas.mission import MISSION_SCHEMA_VERSION
from tests.helpers import make_mission_payload

_RUNNER = CliRunner()


def _legacy_payload() -> dict[str, object]:
    payload = make_mission_payload()
    payload.pop("schema_version", None)
    return payload


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_pure_mission_v6_to_v7_migration_adds_explicit_version() -> None:
    migrated = migrate_mission_v6_to_v7(_legacy_payload())

    assert migrated["schema_version"] == MISSION_SCHEMA_VERSION
    assert "schema_version" not in _legacy_payload()


def test_migration_rejects_sora_20_relabelling_even_when_unapplied() -> None:
    payload = _legacy_payload()
    payload["sora"] = {
        "version": "2.0",
        "ground_risk_mitigations": {
            "m1_strategic": {"applied": False, "robustness": "high"},
            "m2_impact_reduction": {"applied": False, "robustness": "none"},
            "m3_erp": {"applied": False, "robustness": "low"},
        },
        "air_risk": {"tactical_mitigation": {"applied": False, "robustness": "high"}},
    }

    with pytest.raises(ValueError, match="cannot be relabelled"):
        migrate_mission_v6_to_v7(payload)


def test_migration_rejects_legacy_airspace_without_whole_volume_evidence() -> None:
    payload = _legacy_payload()
    payload["airspace"] = {
        "class": "D",
        "max_altitude_agl_m": 120.0,
        "strategic_mitigation": False,
    }

    with pytest.raises(ValueError, match="whole-volume assessment reference"):
        migrate_mission_v6_to_v7(payload)


def test_migration_rejects_implicit_risk_increasing_airspace_flags() -> None:
    payload = _legacy_payload()
    payload["airspace"] = {
        "class": "D",
        "max_altitude_agl_m": 120.0,
        "operational_and_contingency_volume_assessment_reference": "OPS-AIR-16",
        "worst_case_arc_declared": True,
    }

    with pytest.raises(ValueError, match="near_aerodrome=true or false"):
        migrate_mission_v6_to_v7(payload)


def test_migration_preserves_operator_supplied_whole_volume_evidence() -> None:
    payload = _legacy_payload()
    payload["airspace"] = {
        "class": "D",
        "max_altitude_agl_m": 120.0,
        "strategic_mitigation": False,
        "operational_and_contingency_volume_assessment_reference": "OPS-AIR-17",
        "worst_case_arc_declared": True,
        "near_aerodrome": False,
        "transponder_mandatory_zone": False,
    }

    migrated = migrate_mission_v6_to_v7(payload)

    airspace = migrated["airspace"]
    assert isinstance(airspace, dict)
    assert "strategic_mitigation" not in airspace
    assert (
        airspace["operational_and_contingency_volume_assessment_reference"]
        == "OPS-AIR-17"
    )
    assert airspace["worst_case_arc_declared"] is True
    assert airspace["aerodrome_environment"] is False
    assert "near_aerodrome" not in airspace


@pytest.mark.parametrize(
    "field",
    ["m1_strategic", "m3_erp"],
)
def test_migration_rejects_ambiguous_applied_legacy_ground_credit(field: str) -> None:
    payload = _legacy_payload()
    payload["sora"] = {
        "version": "2.5",
        "ground_risk_mitigations": {field: {"applied": True, "robustness": "high"}},
    }

    with pytest.raises(ValueError, match="cannot|no SORA"):
        migrate_mission_v6_to_v7(payload)


def test_migration_rejects_non_boolean_legacy_credit_flag() -> None:
    payload = _legacy_payload()
    payload["sora"] = {
        "version": "2.5",
        "ground_risk_mitigations": {
            "m1_strategic": {"applied": "false", "robustness": "none"}
        },
    }

    with pytest.raises(ValueError, match="applied must be a boolean"):
        migrate_mission_v6_to_v7(payload)


def test_migration_rejects_ambiguous_fl600_boolean() -> None:
    payload = _legacy_payload()
    payload["airspace"] = {
        "class": "A",
        "max_altitude_agl_m": 19_000.0,
        "above_flight_level_600": True,
        "operational_and_contingency_volume_assessment_reference": "OPS-AIR-18",
        "worst_case_arc_declared": True,
        "near_aerodrome": False,
        "transponder_mandatory_zone": False,
    }

    with pytest.raises(ValueError, match="entire operational volume"):
        migrate_mission_v6_to_v7(payload)


@pytest.mark.parametrize("invalid", ["false", 0, 1, [], {}])
def test_migration_rejects_non_boolean_fl600_values(invalid: object) -> None:
    payload = _legacy_payload()
    payload["airspace"] = {
        "class": "A",
        "max_altitude_agl_m": 120.0,
        "above_flight_level_600": invalid,
        "operational_and_contingency_volume_assessment_reference": "OPS-AIR-19",
        "worst_case_arc_declared": True,
        "near_aerodrome": False,
        "transponder_mandatory_zone": False,
    }

    with pytest.raises(ValueError, match="must be a boolean or null"):
        migrate_mission_v6_to_v7(payload)


def test_migrate_cli_rejects_non_string_schema_version(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    payload = _legacy_payload()
    payload["schema_version"] = []
    _write(source, payload)

    result = _RUNNER.invoke(app, ["migrate", str(source), "--dry-run"])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "schema_version must be a string" in result.stderr


def test_migrate_dry_run_prints_diff_without_writing(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    _write(source, _legacy_payload())
    original = source.read_text(encoding="utf-8")

    result = _RUNNER.invoke(app, ["migrate", str(source), "--dry-run"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert f"{MISSION_V6} -> {MISSION_SCHEMA_VERSION}" in result.stdout
    assert "+schema_version: mission.v7" in result.stdout
    assert source.read_text(encoding="utf-8") == original


def test_migrate_output_writes_valid_latest_mission(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    destination = tmp_path / "mission-v7.yaml"
    _write(source, _legacy_payload())

    result = _RUNNER.invoke(
        app,
        ["migrate", str(source), "--output", str(destination)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    mission, _ = load_mission(destination)
    assert mission.schema_version == MISSION_SCHEMA_VERSION
    assert "schema_version" not in yaml.safe_load(source.read_text(encoding="utf-8"))


def test_migrate_latest_input_copies_to_explicit_output(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    destination = tmp_path / "copy.yaml"
    _write(source, make_mission_payload())

    result = _RUNNER.invoke(
        app,
        ["migrate", str(source), "--output", str(destination)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert destination.read_bytes() == source.read_bytes()


def test_migrate_dry_run_never_copies_latest_input(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    destination = tmp_path / "copy.yaml"
    _write(source, make_mission_payload())

    result = _RUNNER.invoke(
        app,
        ["migrate", str(source), "--dry-run", "--output", str(destination)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "would write" in result.stdout
    assert not destination.exists()


def test_migrate_directory_validates_every_file_before_writing(tmp_path: Path) -> None:
    valid_source = tmp_path / "01-valid.yaml"
    invalid_source = tmp_path / "02-invalid.yaml"
    valid_payload = _legacy_payload()
    invalid_payload = _legacy_payload()
    invalid_payload["airspace"] = {
        "class": "D",
        "max_altitude_agl_m": 120.0,
    }
    _write(valid_source, valid_payload)
    _write(invalid_source, invalid_payload)

    result = _RUNNER.invoke(app, ["migrate", str(tmp_path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "whole-volume assessment reference" in result.stderr
    assert "schema_version" not in yaml.safe_load(valid_source.read_text())
    assert "schema_version" not in yaml.safe_load(invalid_source.read_text())


def test_migrate_rejects_unsupported_input_extension(tmp_path: Path) -> None:
    source = tmp_path / "mission.txt"
    source.write_text("schema_version: mission.v7\n", encoding="utf-8")

    result = _RUNNER.invoke(app, ["migrate", str(source)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "use JSON or YAML" in result.stderr


def test_migrate_backup_preserves_original(tmp_path: Path) -> None:
    source = tmp_path / "mission.yaml"
    _write(source, _legacy_payload())
    original = source.read_text(encoding="utf-8")

    result = _RUNNER.invoke(app, ["migrate", str(source), "--backup"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert Path(f"{source}.bak").read_text(encoding="utf-8") == original
    assert (
        yaml.safe_load(source.read_text(encoding="utf-8"))["schema_version"]
        == MISSION_SCHEMA_VERSION
    )


def test_migrate_nonexistent_path_uses_invalid_input_exit() -> None:
    result = _RUNNER.invoke(app, ["migrate", "/definitely/missing/mission.yaml"])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "does not exist" in result.stderr
