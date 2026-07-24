"""Tests for the read-only contract-version discovery command."""

import json
from pathlib import Path
import tempfile

import yaml
from typing import get_args

from typer.testing import CliRunner

from bvlos_sim.adapters.battery_sizing_envelope import BATTERY_SIZING_REPORT_SCHEMA_VERSION
from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.envelope import (
    GEOFENCE_SCHEMA_VERSION,
    LANDING_ZONE_SCHEMA_VERSION,
    MISSION_SCHEMA_VERSION,
    CALIBRATION_SCHEMA_VERSION,
    OBSTACLE_SCHEMA_VERSION,
    POPULATION_SCHEMA_VERSION,
    RESULT_ENVELOPE_SCHEMA_VERSION,
    TERRAIN_SCHEMA_VERSION,
    VEHICLE_SCHEMA_VERSION,
    WIND_GRID_SCHEMA_VERSION,
)
from bvlos_sim.adapters.scenario_envelope import (
    SCENARIO_INPUT_SCHEMA_VERSION,
    SCENARIO_REPORT_SCHEMA_VERSION,
)
from bvlos_sim.adapters.sitl.evidence import SITL_EVIDENCE_SCHEMA_VERSION
from bvlos_sim.adapters.stochastic_envelope import (
    STOCHASTIC_ENVELOPE_SCHEMA_VERSION,
    STOCHASTIC_INPUT_SCHEMA_VERSION,
)
from bvlos_sim.adapters.sora_envelope import SORA_ENVELOPE_SCHEMA_VERSION
from bvlos_sim.adapters.uncertainty_envelope import (
    UNCERTAINTY_INPUT_SCHEMA_VERSION,
    UNCERTAINTY_REPORT_SCHEMA_VERSION,
)
from bvlos_sim.adapters.version import tool_version
from bvlos_sim.schemas.batch import BatchManifest
from bvlos_sim.schemas.calibration import CALIBRATION_PROFILE_SCHEMA_VERSION
from bvlos_sim.schemas.flight_log import FLIGHT_TRACE_SCHEMA_VERSION
from bvlos_sim.schemas.phase_segment import PHASE_SEGMENT_SCHEMA_VERSION
from bvlos_sim.schemas.sitl_comparison import SITL_COMPARISON_SCHEMA_VERSION
from bvlos_sim.schemas.sora import SORA_ASSESSMENT_SCHEMA_VERSION
from bvlos_sim.schemas.validation import VALIDATION_REPORT_SCHEMA_VERSION

runner = CliRunner()


def _invoke(command: str):
    return runner.invoke(app, [command])


def test_schema_versions_exits_zero_and_emits_json() -> None:
    result = _invoke("schema-versions")
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.stdout)
    assert set(payload) == {"tool_version", "output_envelopes", "input_schemas"}


def test_schema_versions_needs_no_file_argument() -> None:
    # The bare command succeeds with no mission/vehicle/asset path.
    result = _invoke("schema-versions")
    assert result.exit_code == int(CliExitCode.SUCCESS)


def test_tool_version_matches_resolver() -> None:
    payload = json.loads(_invoke("schema-versions").stdout)
    assert payload["tool_version"] == tool_version()


def test_output_envelope_versions_match_constants() -> None:
    envelopes = json.loads(_invoke("schema-versions").stdout)["output_envelopes"]
    assert envelopes == {
        "estimator": RESULT_ENVELOPE_SCHEMA_VERSION,
        "scenario_report": SCENARIO_REPORT_SCHEMA_VERSION,
        "uncertainty_report": UNCERTAINTY_REPORT_SCHEMA_VERSION,
        "stochastic_envelope": STOCHASTIC_ENVELOPE_SCHEMA_VERSION,
        "sora_envelope": SORA_ENVELOPE_SCHEMA_VERSION,
        "battery_sizing_report": BATTERY_SIZING_REPORT_SCHEMA_VERSION,
        "sitl_evidence": SITL_EVIDENCE_SCHEMA_VERSION,
        "sitl_comparison": SITL_COMPARISON_SCHEMA_VERSION,
        "validation_report": VALIDATION_REPORT_SCHEMA_VERSION,
        "calibration_profile": CALIBRATION_PROFILE_SCHEMA_VERSION,
        "flight_trace": FLIGHT_TRACE_SCHEMA_VERSION,
        "phase_segments": PHASE_SEGMENT_SCHEMA_VERSION,
        "sora_assessment": SORA_ASSESSMENT_SCHEMA_VERSION,
    }


def test_input_schema_versions_match_constants() -> None:
    inputs = json.loads(_invoke("schema-versions").stdout)["input_schemas"]
    batch_version = get_args(BatchManifest.model_fields["format_version"].annotation)[0]
    assert inputs == {
        "mission": MISSION_SCHEMA_VERSION,
        "vehicle": VEHICLE_SCHEMA_VERSION,
        "geofences": GEOFENCE_SCHEMA_VERSION,
        "landing_zones": LANDING_ZONE_SCHEMA_VERSION,
        "terrain": TERRAIN_SCHEMA_VERSION,
        "population": POPULATION_SCHEMA_VERSION,
        "wind_grid": WIND_GRID_SCHEMA_VERSION,
        "obstacles": OBSTACLE_SCHEMA_VERSION,
        "calibration": CALIBRATION_SCHEMA_VERSION,
        "scenario": SCENARIO_INPUT_SCHEMA_VERSION,
        "uncertainty": UNCERTAINTY_INPUT_SCHEMA_VERSION,
        "stochastic": STOCHASTIC_INPUT_SCHEMA_VERSION,
        "batch": batch_version,
    }


def test_contracts_alias_matches_schema_versions() -> None:
    primary = _invoke("schema-versions")
    alias = _invoke("contracts")
    assert alias.exit_code == int(CliExitCode.SUCCESS)
    assert alias.stdout == primary.stdout


def test_output_is_deterministic() -> None:
    first = _invoke("schema-versions")
    second = _invoke("schema-versions")
    assert first.stdout == second.stdout


def test_version_flag_unchanged() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"bvlos-sim {tool_version()}"


def test_population_schema_version_matches_the_loader() -> None:
    """The advertised version must be the one the loader actually accepts.

    Comparing the CLI output to the same constants is tautological, so the
    constant drifted to population-grid.v1 while the loader required v2 and
    rejected v1 assets with exit 11.
    """

    import pytest

    from bvlos_sim.adapters.assets.population_grid import (
        PopulationGridLoadError,
        load_population_grid,
    )

    asset = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "missions"
        / "assets"
        / "pipeline_population_grid.yaml"
    )
    base = yaml.safe_load(asset.read_text())
    assert base["schema_version"] == POPULATION_SCHEMA_VERSION
    tmp = Path(tempfile.mkdtemp())

    load_population_grid(asset)  # the advertised version really loads

    stale = tmp / "stale.yaml"
    stale.write_text(
        yaml.safe_dump(dict(base, schema_version="population-grid.v1")),
        encoding="utf-8",
    )
    with pytest.raises(PopulationGridLoadError):
        load_population_grid(stale)
