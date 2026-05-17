"""SITL-specific CLI support helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from adapters.ardupilot_sitl_types import ArduPilotSitlConfig
from adapters.cli_support import (
    MissionAssetBundle,
    SitlScenarioContext,
    _build_scenario_result_envelope,
    _populate_mission_assets,
    _resolve_scenario_input_paths,
    _run_scenario_with_assets,
)
from adapters.envelope import OutputFormat
from adapters.io import load_mission, load_vehicle
from adapters.scenario_io import load_scenario
from adapters.sitl_comparison import render_sitl_comparison_json
from adapters.sitl_comparison_markdown import render_sitl_comparison_markdown
from adapters.sitl_evidence import (
    SitlAdapter,
    build_sitl_evidence_bundle,
    render_sitl_evidence_json,
)
from adapters.sitl_evidence_markdown import render_sitl_evidence_markdown
from schemas import MissionPlan, SitlComparisonReport, SitlComparisonSummary
from schemas import SitlEvidenceBundle

ComparisonRenderer = Callable[[SitlComparisonReport], str]
EvidenceRenderer = Callable[[SitlEvidenceBundle], str]

_EXIT_SUCCESS = 0
_EXIT_INFEASIBLE = 10
_EXIT_UNSUPPORTED = 12
_EXIT_INTERNAL_ERROR = 13


@dataclass(frozen=True)
class SitlLiveOptions:
    """Live SITL connection and artifact recording options."""

    host: str
    port: int
    artifact_dir: Path
    telemetry_samples: int
    telemetry_timeout_s: float


_SITL_COMPARISON_RENDERERS: dict[OutputFormat, ComparisonRenderer] = {
    OutputFormat.JSON: render_sitl_comparison_json,
    OutputFormat.MARKDOWN: render_sitl_comparison_markdown,
}

_SITL_EVIDENCE_RENDERERS: dict[OutputFormat, EvidenceRenderer] = {
    OutputFormat.JSON: render_sitl_evidence_json,
    OutputFormat.MARKDOWN: render_sitl_evidence_markdown,
}
_SITL_COMPARISON_EXIT_CODES = {
    SitlComparisonSummary.PASSED: _EXIT_SUCCESS,
    SitlComparisonSummary.DRIFTED: _EXIT_INFEASIBLE,
    SitlComparisonSummary.FAILED: _EXIT_INFEASIBLE,
    SitlComparisonSummary.UNSUPPORTED: _EXIT_UNSUPPORTED,
}


def _render_sitl_evidence_output(
    output_format: OutputFormat,
    bundle: SitlEvidenceBundle,
) -> str:
    return _SITL_EVIDENCE_RENDERERS[output_format](bundle)


def _render_sitl_comparison_output(
    output_format: OutputFormat,
    report: SitlComparisonReport,
) -> str:
    return _SITL_COMPARISON_RENDERERS[output_format](report)


def _exit_code_for_comparison_report(report: SitlComparisonReport) -> int:
    return _SITL_COMPARISON_EXIT_CODES.get(report.summary, _EXIT_INTERNAL_ERROR)


def _resolve_sitl_live_options(
    *,
    live: bool,
    host: str,
    port: int,
    artifact_dir: Path | None,
    telemetry_samples: int,
    telemetry_timeout_s: float,
) -> SitlLiveOptions | None:
    if not live or artifact_dir is None:
        return None
    return SitlLiveOptions(
        host=host,
        port=port,
        artifact_dir=artifact_dir,
        telemetry_samples=telemetry_samples,
        telemetry_timeout_s=telemetry_timeout_s,
    )


def _load_sitl_scenario_context(scenario_file: Path) -> SitlScenarioContext:
    scenario_plan, scenario_document = load_scenario(scenario_file)
    mission_path, vehicle_path = _resolve_scenario_input_paths(
        scenario_plan,
        scenario_file=scenario_file,
    )
    mission_model, mission_document = load_mission(mission_path)
    vehicle_model, vehicle_document = load_vehicle(vehicle_path)
    mission_assets = MissionAssetBundle()
    _populate_mission_assets(
        mission_assets,
        mission_model=mission_model,
        mission_document=mission_document,
    )
    scenario_result = _run_scenario_with_assets(
        scenario_plan=scenario_plan,
        mission_model=mission_model,
        vehicle_model=vehicle_model,
        mission_assets=mission_assets,
    )
    scenario_envelope = _build_scenario_result_envelope(
        result=scenario_result,
        scenario_document=scenario_document,
        mission_document=mission_document,
        vehicle_document=vehicle_document,
        mission_assets=mission_assets,
    )
    return SitlScenarioContext(
        scenario_plan=scenario_plan,
        scenario_document=scenario_document,
        mission_model=mission_model,
        mission_document=mission_document,
        vehicle_model=vehicle_model,
        vehicle_document=vehicle_document,
        mission_assets=mission_assets,
        scenario_envelope=scenario_envelope,
    )


def _emit_sitl_progress(message: str) -> None:
    typer.echo(f"[sitl] {message}", err=True)


def _record_live_sitl_artifacts(
    mission_model: MissionPlan,
    options: SitlLiveOptions,
) -> SitlAdapter:
    from adapters.ardupilot_sitl import ArduPilotSitlAdapter

    adapter = ArduPilotSitlAdapter(
        ArduPilotSitlConfig(host=options.host, port=options.port)
    )
    adapter.start_recording(options.artifact_dir)
    try:
        _emit_sitl_progress(f"Connecting to {options.host}:{options.port}...")
        adapter.connect()
        _emit_sitl_progress(f"Uploading mission ({len(mission_model.route)} items)...")
        adapter.upload_mission(mission_model)
        _emit_sitl_progress(
            f"Recording telemetry ({options.telemetry_samples} samples)..."
        )
        adapter.record_telemetry(
            sample_count=options.telemetry_samples,
            timeout_s=options.telemetry_timeout_s,
        )
    finally:
        try:
            adapter.disconnect()
        except Exception:
            pass
    return adapter


def _sitl_adapter_for_options(
    context: SitlScenarioContext,
    live_options: SitlLiveOptions | None,
) -> SitlAdapter | None:
    if live_options is None:
        return None
    return _record_live_sitl_artifacts(context.mission_model, live_options)


def _build_sitl_evidence_from_context(
    context: SitlScenarioContext,
    *,
    adapter: SitlAdapter | None,
    live_options: SitlLiveOptions | None,
) -> SitlEvidenceBundle:
    suffix = "contract" if live_options is None else "live"
    evidence_id = f"{context.scenario_plan.scenario_id}-sitl-{suffix}"
    return build_sitl_evidence_bundle(
        evidence_id=evidence_id,
        scenario_envelope=context.scenario_envelope,
        scenario_document=context.scenario_document,
        mission_document=context.mission_document,
        vehicle_document=context.vehicle_document,
        vehicle=context.vehicle_model,
        geofence_document=context.mission_assets.geofence_document,
        landing_zone_document=context.mission_assets.landing_zone_document,
        terrain_document=context.mission_assets.terrain_document,
        wind_grid_document=context.mission_assets.wind_grid_document,
        adapter=adapter,
    )


__all__ = [
    "ComparisonRenderer",
    "EvidenceRenderer",
    "SitlLiveOptions",
    "_SITL_COMPARISON_EXIT_CODES",
    "_SITL_COMPARISON_RENDERERS",
    "_SITL_EVIDENCE_RENDERERS",
    "_build_sitl_evidence_from_context",
    "_emit_sitl_progress",
    "_exit_code_for_comparison_report",
    "_load_sitl_scenario_context",
    "_record_live_sitl_artifacts",
    "_render_sitl_comparison_output",
    "_render_sitl_evidence_output",
    "_resolve_sitl_live_options",
    "_sitl_adapter_for_options",
]
