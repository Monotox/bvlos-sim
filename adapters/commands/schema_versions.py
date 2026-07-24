"""Read-only contract-version discovery command.

Prints the supported input and output contract versions plus the tool version as
canonical JSON, then exits 0 without loading any mission or vehicle file. A
backend can call this at startup to pin and check contract compatibility instead
of inferring versions from a full run's envelope.
"""

from typing import get_args

import typer

import adapters.cli as cli
from adapters.battery_sizing_envelope import BATTERY_SIZING_REPORT_SCHEMA_VERSION
from adapters.canonical_json import render_canonical_json
from adapters.envelope import (
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
from adapters.scenario_envelope import (
    SCENARIO_INPUT_SCHEMA_VERSION,
    SCENARIO_REPORT_SCHEMA_VERSION,
)
from adapters.sitl.evidence import SITL_EVIDENCE_SCHEMA_VERSION
from adapters.stochastic_envelope import (
    STOCHASTIC_ENVELOPE_SCHEMA_VERSION,
    STOCHASTIC_INPUT_SCHEMA_VERSION,
)
from adapters.sora_envelope import SORA_ENVELOPE_SCHEMA_VERSION
from adapters.uncertainty_envelope import (
    UNCERTAINTY_INPUT_SCHEMA_VERSION,
    UNCERTAINTY_REPORT_SCHEMA_VERSION,
)
from adapters.version import tool_version
from schemas.batch import BatchManifest
from schemas.calibration import CALIBRATION_PROFILE_SCHEMA_VERSION
from schemas.flight_log import FLIGHT_TRACE_SCHEMA_VERSION
from schemas.phase_segment import PHASE_SEGMENT_SCHEMA_VERSION
from schemas.sitl_comparison import SITL_COMPARISON_SCHEMA_VERSION
from schemas.sora import SORA_ASSESSMENT_SCHEMA_VERSION
from schemas.validation import VALIDATION_REPORT_SCHEMA_VERSION

# The batch manifest carries its version as a Literal field rather than a named
# constant; source it from the field annotation so the discovery map cannot drift
# from what the loader actually accepts, without re-stating the string here.
BATCH_INPUT_SCHEMA_VERSION = get_args(
    BatchManifest.model_fields["format_version"].annotation
)[0]


def _output_envelope_versions() -> dict[str, str]:
    return {
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


def _input_schema_versions() -> dict[str, str]:
    return {
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
        "batch": BATCH_INPUT_SCHEMA_VERSION,
    }


def _contract_versions() -> dict[str, object]:
    return {
        "tool_version": tool_version(),
        "output_envelopes": _output_envelope_versions(),
        "input_schemas": _input_schema_versions(),
    }


def schema_versions() -> None:
    """Print supported contract versions as canonical JSON and exit 0.

    Read-only discovery: loads no mission, vehicle, or asset file. The printed
    versions are sourced from the same module constants the envelopes emit, so the
    map cannot drift from what a real run would produce.
    """
    typer.echo(render_canonical_json(_contract_versions()), nl=False)
    raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
