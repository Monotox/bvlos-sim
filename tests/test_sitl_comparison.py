"""SITL comparison report tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pyproj import Geod

from adapters.sitl.comparison import (
    build_sitl_comparison_report,
    render_sitl_comparison_json,
)
from adapters.sitl.comparison_markdown import render_sitl_comparison_markdown
from adapters.sitl.evidence import compare_sitl_evidence_bundle
from schemas import (
    SitlAdapterKind,
    SitlArtifactReference,
    SitlArtifactRole,
    SitlComparisonOutcome,
    SitlComparisonReport,
    SitlComparisonSummary,
    SitlEvidenceBundle,
    SitlEvidenceStatus,
    SitlExpectedOutputs,
    SitlObservedArtifacts,
    SitlSimulatorMetadata,
)
from schemas.sitl import SitlJsonValue

type JsonObject = dict[str, SitlJsonValue]

_GEOD = Geod(ellps="WGS84")


def _write_telemetry(tmp_path: Path, records: list[JsonObject]) -> Path:
    path = tmp_path / "telemetry.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "sitl-telemetry.v1",
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_command_log(tmp_path: Path, commands: list[JsonObject]) -> Path:
    path = tmp_path / "command_log.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "sitl-command-log.v1",
                "commands": commands,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_simulator_log(tmp_path: Path, events: list[JsonObject]) -> Path:
    path = tmp_path / "simulator_log.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "sitl-simulator-log.v1",
                "events": events,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_adapter_log(tmp_path: Path, events: list[JsonObject]) -> Path:
    path = tmp_path / "adapter_log.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "sitl-adapter-log.v1",
                "events": events,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _artifact_ref(
    path: Path,
    role: SitlArtifactRole,
    schema_version: str,
) -> SitlArtifactReference:
    return SitlArtifactReference(
        role=role,
        path=str(path),
        format="json",
        schema_version=schema_version,
    )


def _scenario_report(
    *,
    assertion_passed: bool = True,
) -> JsonObject:
    return {
        "scenario_id": "comparison-test",
        "status": "passed" if assertion_passed else "failed",
        "timeline": [
            {
                "index": 0,
                "elapsed_time_s": 0.0,
                "lat": 52.0,
                "lon": 4.0,
                "altitude_amsl_m": 12.0,
            },
            {
                "index": 1,
                "elapsed_time_s": 10.0,
                "lat": 52.001,
                "lon": 4.001,
                "altitude_amsl_m": 50.0,
            },
        ],
        "assertion_results": [
            {
                "assertion_id": "time-under-limit",
                "passed": assertion_passed,
                "field_path": "estimate.total_time_s",
                "expected_value": 3600.0,
                "observed_value": 120.0,
            }
        ],
        "event_outcomes": [],
        "estimate": None,
    }


def _telemetry_record(
    message_type: str,
    fields: JsonObject | None = None,
) -> JsonObject:
    return {
        "timestamp_s": 1.0,
        "message_type": message_type,
        "fields": fields or {},
    }


def _simulator_metadata() -> SitlSimulatorMetadata:
    return SitlSimulatorMetadata(
        adapter_kind=SitlAdapterKind.ARDUPILOT,
        adapter_id="ardupilot-sitl-test",
        adapter_version="0.1.0",
        execution_mode="live_sitl",
        simulator_name="ArduPilot SITL",
        simulator_version=None,
        autopilot="ardupilot",
        frame="quad",
        metadata={},
    )


def _completed_bundle(
    tmp_path: Path,
    *,
    assertion_passed: bool = True,
    telemetry_records: list[JsonObject] | None = None,
    commands: list[JsonObject] | None = None,
    adapter_events: list[JsonObject] | None = None,
    simulator_events: list[JsonObject] | None = None,
) -> SitlEvidenceBundle:
    telemetry = telemetry_records or [
        _telemetry_record("HEARTBEAT"),
        _telemetry_record(
            "GLOBAL_POSITION_INT",
            {"lat": 520010000, "lon": 40010000},
        ),
    ]
    command_log = commands or [
        {
            "timestamp_s": 1.5,
            "command": "MISSION_COUNT",
            "fields": {"item_count": 1},
        }
    ]
    adapter_log = adapter_events or [
        {"timestamp_s": 0.0, "event": "adapter_initialized"},
        {"timestamp_s": 0.1, "event": "recording_started"},
    ]
    simulator_log = simulator_events or [
        {"timestamp_s": 0.2, "event": "connected"},
    ]

    return SitlEvidenceBundle(
        schema_version="sitl-evidence.v1",
        evidence_id="comparison-test-evidence",
        status=SitlEvidenceStatus.COMPLETED,
        tool_version="0.2.0",
        created_by="pytest",
        inputs=[],
        expected=SitlExpectedOutputs(
            scenario_report=_scenario_report(assertion_passed=assertion_passed),
            estimator_result=None,
        ),
        simulator=_simulator_metadata(),
        observed=SitlObservedArtifacts(
            telemetry=[
                _artifact_ref(
                    _write_telemetry(tmp_path, telemetry),
                    SitlArtifactRole.TELEMETRY,
                    "sitl-telemetry.v1",
                )
            ],
            command_logs=[
                _artifact_ref(
                    _write_command_log(tmp_path, command_log),
                    SitlArtifactRole.COMMAND_LOG,
                    "sitl-command-log.v1",
                )
            ],
            simulator_logs=[
                _artifact_ref(
                    _write_simulator_log(tmp_path, simulator_log),
                    SitlArtifactRole.SIMULATOR_LOG,
                    "sitl-simulator-log.v1",
                )
            ],
            adapter_logs=[
                _artifact_ref(
                    _write_adapter_log(tmp_path, adapter_log),
                    SitlArtifactRole.ADAPTER_LOG,
                    "sitl-adapter-log.v1",
                )
            ],
        ),
    )


def _contract_only_bundle() -> SitlEvidenceBundle:
    return SitlEvidenceBundle(
        schema_version="sitl-evidence.v1",
        evidence_id="comparison-contract-only",
        status=SitlEvidenceStatus.CONTRACT_ONLY,
        tool_version="0.2.0",
        created_by="pytest",
        inputs=[],
        expected=SitlExpectedOutputs(
            scenario_report=_scenario_report(),
            estimator_result=None,
        ),
        simulator=_simulator_metadata(),
        observed=SitlObservedArtifacts(),
    )


def _report_for(bundle: SitlEvidenceBundle) -> dict[str, SitlComparisonOutcome]:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=bundle,
    )
    return {item.dimension: item.outcome for item in report.items}


def test_contract_only_bundle_marks_telemetry_dimensions_skipped() -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_contract_only_bundle(),
    )
    outcomes = {item.dimension: item.outcome for item in report.items}

    assert outcomes["bundle_completeness"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["mission_item_count"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["telemetry_record_count"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["heartbeat_observed"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["adapter_lifecycle"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["simulator_lifecycle"] == SitlComparisonOutcome.SKIPPED
    assert outcomes["position_proximity"] == SitlComparisonOutcome.SKIPPED
    assert report.summary != SitlComparisonSummary.FAILED


def test_completed_bundle_matched_scenario_assertions_pass(tmp_path: Path) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(tmp_path),
    )

    assertion_items = [
        item for item in report.items if item.dimension.startswith("assertion:")
    ]
    assert assertion_items
    assert all(
        item.outcome == SitlComparisonOutcome.MATCHED for item in assertion_items
    )
    assert report.summary == SitlComparisonSummary.PASSED


def test_completed_bundle_failed_assertion_does_not_cause_summary_failed(
    tmp_path: Path,
) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(tmp_path, assertion_passed=False),
    )
    assertion = next(
        item for item in report.items if item.dimension == "assertion:time-under-limit"
    )

    assert assertion.outcome == SitlComparisonOutcome.MISSING
    assert report.summary == SitlComparisonSummary.FAILED


def test_mission_item_count_matched(tmp_path: Path) -> None:
    outcomes = _report_for(_completed_bundle(tmp_path))

    assert outcomes["mission_item_count"] == SitlComparisonOutcome.MATCHED


def test_mission_item_count_missing_when_no_mission_count_command(
    tmp_path: Path,
) -> None:
    outcomes = _report_for(
        _completed_bundle(
            tmp_path,
            commands=[
                {
                    "timestamp_s": 1.5,
                    "command": "MISSION_ITEM_INT",
                    "fields": {"seq": 0},
                }
            ],
        )
    )

    assert outcomes["mission_item_count"] == SitlComparisonOutcome.MISSING


def test_heartbeat_missing_when_no_heartbeat_in_telemetry(tmp_path: Path) -> None:
    outcomes = _report_for(
        _completed_bundle(
            tmp_path,
            telemetry_records=[
                _telemetry_record(
                    "GLOBAL_POSITION_INT",
                    {"lat": 520010000, "lon": 40010000},
                )
            ],
        )
    )

    assert outcomes["heartbeat_observed"] == SitlComparisonOutcome.MISSING


def test_position_proximity_matched_when_within_tolerance(tmp_path: Path) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(
            tmp_path,
            telemetry_records=[
                _telemetry_record("HEARTBEAT"),
                _telemetry_record(
                    "GLOBAL_POSITION_INT",
                    {"lat": 520010000, "lon": 40010000},
                ),
            ],
        ),
    )

    assert any(
        item.dimension.startswith("position:")
        and item.outcome == SitlComparisonOutcome.MATCHED
        for item in report.items
    )


def test_position_proximity_drifted_when_outside_tolerance(tmp_path: Path) -> None:
    lon, lat, _back_azimuth = _GEOD.fwd(4.001, 52.001, 90.0, 800.0)
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(
            tmp_path,
            telemetry_records=[
                _telemetry_record("HEARTBEAT"),
                _telemetry_record(
                    "GLOBAL_POSITION_INT",
                    {"lat": round(lat * 10_000_000), "lon": round(lon * 10_000_000)},
                ),
            ],
        ),
    )
    position = next(
        item for item in report.items if item.dimension.startswith("position:")
    )

    assert position.outcome == SitlComparisonOutcome.DRIFTED


def test_position_proximity_unsupported_when_no_global_position_int(
    tmp_path: Path,
) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(
            tmp_path,
            telemetry_records=[_telemetry_record("HEARTBEAT")],
        ),
    )
    position_items = [
        item
        for item in report.items
        if item.dimension == "position_proximity"
        or item.dimension.startswith("position:")
    ]

    assert len(position_items) == 1
    assert position_items[0].dimension == "position_proximity"
    assert position_items[0].outcome == SitlComparisonOutcome.UNSUPPORTED


def test_render_sitl_comparison_json_is_deterministic(tmp_path: Path) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(tmp_path),
    )
    rendered = render_sitl_comparison_json(report)

    assert rendered == render_sitl_comparison_json(report)
    assert json.loads(rendered)["schema_version"] == "sitl-comparison.v1"


def test_render_sitl_comparison_markdown_contains_summary(tmp_path: Path) -> None:
    report = compare_sitl_evidence_bundle(
        _completed_bundle(tmp_path),
        comparison_id="comparison-report",
    )
    rendered = render_sitl_comparison_markdown(report)

    assert "SITL Comparison Report" in rendered
    assert report.summary.value in rendered


def test_sitl_comparison_report_rejects_unknown_fields(tmp_path: Path) -> None:
    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_completed_bundle(tmp_path),
    )
    payload = report.model_dump(mode="json")

    with pytest.raises(ValidationError):
        SitlComparisonReport.model_validate({**payload, "unexpected": True})


def test_contract_only_bundle_skipped_dimensions_cover_telemetry_dependent_list() -> None:
    from adapters.sitl.comparison_dimensions import _TELEMETRY_DEPENDENT_DIMENSIONS

    report = build_sitl_comparison_report(
        comparison_id="comparison-report",
        bundle=_contract_only_bundle(),
    )
    skipped = {item.dimension for item in report.items if item.outcome == SitlComparisonOutcome.SKIPPED}

    assert set(_TELEMETRY_DEPENDENT_DIMENSIONS) <= skipped
