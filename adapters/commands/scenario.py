"""Deterministic scenario command."""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import typer

import adapters.cli as cli
from adapters.calibration import load_and_apply_calibration, load_calibration_profile
from adapters.checklist_markdown import checklist_is_go
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _build_scenario_result_envelope,
    _envelope_output_format,
    _input_error_for_geojson_asset_error,
    _populate_mission_assets,
    _render_scenario_output,
    _resolve_scenario_input_paths,
    _run_scenario_with_assets,
    _write_output,
)
from adapters.envelope import OutputFormat
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.geojson_export import build_geojson_export
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.kml_export import build_kml_export
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.preflight import (
    check_file,
    emit_preflight,
    is_json_format,
    mission_asset_checks,
)
from adapters.profile_markdown import render_profile_markdown_from_scenario
from adapters.scenario_envelope import (
    ScenarioResultEnvelope,
    build_scenario_internal_error_envelope,
    build_scenario_invalid_input_envelope,
)
from adapters.scenario_io import load_scenario
from estimator import (
    GeofenceZone,
    LandingZone,
    MissionEstimate,
    ScenarioResult,
    ScenarioStatus,
)


class RouteExportBuilder(Protocol):
    def __call__(
        self,
        estimate: MissionEstimate,
        *,
        geofence_zones: list[GeofenceZone] | None = None,
        landing_zones: list[LandingZone] | None = None,
    ) -> str: ...


ScenarioOutputRenderer = Callable[
    [ScenarioResultEnvelope, ScenarioResult, MissionAssetBundle], str
]


def _render_scenario_profile_output(
    envelope: ScenarioResultEnvelope,
    _result: ScenarioResult,
    mission_assets: MissionAssetBundle,
) -> str:
    return render_profile_markdown_from_scenario(
        envelope, terrain_provider=mission_assets.terrain_provider
    )


def _render_scenario_route_export(
    envelope: ScenarioResultEnvelope,
    result: ScenarioResult,
    mission_assets: MissionAssetBundle,
    builder: RouteExportBuilder,
) -> str:
    if result.estimate is None:
        return _render_scenario_output(OutputFormat.JSON, envelope)
    return builder(
        result.estimate,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )


def _render_scenario_geojson_output(
    envelope: ScenarioResultEnvelope,
    result: ScenarioResult,
    mission_assets: MissionAssetBundle,
) -> str:
    if result.estimate is None:
        return _render_scenario_output(OutputFormat.JSON, envelope)
    return build_geojson_export(
        result.estimate,
        geofence_zones=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
        obstacles=mission_assets.obstacle_provider.obstacles()
        if mission_assets.obstacle_provider is not None
        else None,
    )


def _render_scenario_kml_output(
    envelope: ScenarioResultEnvelope,
    result: ScenarioResult,
    mission_assets: MissionAssetBundle,
) -> str:
    return _render_scenario_route_export(
        envelope, result, mission_assets, build_kml_export
    )


_SCENARIO_OUTPUT_RENDERERS: dict[OutputFormat, ScenarioOutputRenderer] = {
    OutputFormat.PROFILE: _render_scenario_profile_output,
    OutputFormat.GEOJSON: _render_scenario_geojson_output,
    OutputFormat.KML: _render_scenario_kml_output,
}


def _render_scenario_command_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
    result: ScenarioResult,
    mission_assets: MissionAssetBundle,
) -> str:
    renderer = _SCENARIO_OUTPUT_RENDERERS.get(output_format)
    if renderer is None:
        return _render_scenario_output(output_format, envelope)
    return renderer(envelope, result, mission_assets)


def _render_scenario_error_output(
    output_format: OutputFormat,
    envelope: ScenarioResultEnvelope,
) -> str:
    return _render_scenario_output(_envelope_output_format(output_format), envelope)


def _emit_scenario_internal_error(
    *,
    output_format: OutputFormat,
    scenario_id: str,
    scenario_document: InputDocument | None,
    mission_document: InputDocument | None,
    vehicle_document: InputDocument | None,
) -> None:
    internal_envelope = build_scenario_internal_error_envelope(
        scenario_id=scenario_id,
        known_documents={
            "scenario": scenario_document,
            "mission": mission_document,
            "vehicle": vehicle_document,
        },
    )
    _write_output(_render_scenario_error_output(output_format, internal_envelope), None)


def _scenario_exit_code_for_result(
    result: ScenarioResult,
    *,
    engineering_only: bool = False,
) -> cli.ScenarioExitCode:
    if result.status == ScenarioStatus.PASSED:
        if not engineering_only and (
            result.estimate is None or not checklist_is_go(result.estimate)
        ):
            return cli.ScenarioExitCode.FAILED
        return cli.ScenarioExitCode.PASSED
    return cli.ScenarioExitCode.FAILED


def _run_scenario_preflight(
    *,
    scenario_file: Path,
    calibration: Path | None,
    as_json: bool,
) -> None:
    """Validate scenario, mission, vehicle, calibration, and assets, no run."""
    files = []
    text_lines = []

    scenario_check, scenario_loaded = check_file(
        role="scenario",
        path_str=scenario_file.name,
        loader=lambda: load_scenario(scenario_file),
    )
    files.append(scenario_check)
    if scenario_check.ok and scenario_loaded is not None:
        text_lines.append(f"scenario: {scenario_file.name}: OK")
        scenario_plan = scenario_loaded[0]
        mission_path, vehicle_path = _resolve_scenario_input_paths(
            scenario_plan, scenario_file=scenario_file
        )
        mission_check, mission_result = check_file(
            role="mission",
            path_str=mission_path.name,
            loader=lambda: load_mission(mission_path),
        )
        files.append(mission_check)
        if mission_check.ok:
            text_lines.append(f"mission: {mission_path.name}: OK")
        vehicle_check, _ = check_file(
            role="vehicle",
            path_str=vehicle_path.name,
            loader=lambda: load_vehicle(vehicle_path),
        )
        files.append(vehicle_check)
        if vehicle_check.ok:
            text_lines.append(f"vehicle: {vehicle_path.name}: OK")
        if calibration is not None:
            calibration_check, _ = check_file(
                role="calibration",
                path_str=calibration.name,
                loader=lambda: load_calibration_profile(calibration),
            )
            files.append(calibration_check)
            if calibration_check.ok:
                text_lines.append(f"calibration: {calibration.name}: OK")
        if mission_result is not None:
            files.extend(
                mission_asset_checks(mission_result[0], mission_path=mission_path)
            )

    emit_preflight(
        command="scenario", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def scenario(
    scenario_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to scenario.v1 YAML file.",
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.JSON,
        "--format",
        help="Output format. Use summary for a one-line result, checklist for pre-flight go/no-go.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    engineering_only: bool = typer.Option(
        False,
        "--engineering-only",
        help=(
            "Return success for a computationally passing scenario even when "
            "operational evidence is missing. Default behavior is fail-closed "
            "GO/NO-GO evaluation for every output format."
        ),
    ),
    calibration: Path | None = typer.Option(
        None,
        "--calibration",
        exists=True,
        readable=True,
        resolve_path=True,
        help=(
            "Optional calibration-profile.v1 JSON to layer on the vehicle. "
            "Overrides matching performance fields; must reference this vehicle_id."
        ),
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate scenario, mission, and vehicle files (and referenced assets) "
            "against their schemas and exit without running the scenario. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Run the deterministic scenario runner and emit a scenario result envelope."""

    if validate_only:
        _run_scenario_preflight(
            scenario_file=scenario_file,
            calibration=calibration,
            as_json=is_json_format(validate_format),
        )

    if format == OutputFormat.SENSITIVITY:
        cli._exit_with_cli_error(
            "--format sensitivity is only supported by estimate.",
            command="scenario",
            code=cli.CliExitCode.INVALID_INPUT,
        )

    scenario_document: InputDocument | None = None
    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    scenario_id = "<unknown>"

    try:
        scenario_plan, scenario_document = load_scenario(scenario_file)
        scenario_id = scenario_plan.scenario_id

        mission_path, vehicle_path = _resolve_scenario_input_paths(
            scenario_plan,
            scenario_file=scenario_file,
        )
        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)
        if calibration is not None:
            vehicle_model = load_and_apply_calibration(vehicle_model, calibration)

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        result = _run_scenario_with_assets(
            scenario_plan=scenario_plan,
            mission_model=mission_model,
            vehicle_model=vehicle_model,
            mission_assets=mission_assets,
        )
        envelope = _build_scenario_result_envelope(
            result=result,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            mission_assets=mission_assets,
        )
        _write_output(
            _render_scenario_command_output(format, envelope, result, mission_assets),
            output,
        )
        raise typer.Exit(
            code=int(
                _scenario_exit_code_for_result(
                    result,
                    engineering_only=engineering_only,
                )
            )
        )
    except InputLoadError as exc:
        envelope = build_scenario_invalid_input_envelope(
            scenario_id=scenario_id,
            error=exc,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            known_documents=mission_assets.known_documents(),
        )
        try:
            _write_output(_render_scenario_error_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _emit_scenario_internal_error(
                output_format=format,
                scenario_id=scenario_id,
                scenario_document=scenario_document,
                mission_document=mission_document,
                vehicle_document=vehicle_document,
            )
            raise typer.Exit(
                code=int(cli.ScenarioExitCode.INTERNAL_ERROR)
            ) from write_exc
        raise typer.Exit(code=int(cli.ScenarioExitCode.INVALID_INPUT)) from exc
    except (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError) as exc:
        envelope = build_scenario_invalid_input_envelope(
            scenario_id=scenario_id,
            error=_input_error_for_geojson_asset_error(exc),
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            known_documents=mission_assets.known_documents(),
        )
        try:
            _write_output(_render_scenario_error_output(format, envelope), output)
        except OutputWriteError as write_exc:
            _emit_scenario_internal_error(
                output_format=format,
                scenario_id=scenario_id,
                scenario_document=scenario_document,
                mission_document=mission_document,
                vehicle_document=vehicle_document,
            )
            raise typer.Exit(
                code=int(cli.ScenarioExitCode.INTERNAL_ERROR)
            ) from write_exc
        raise typer.Exit(code=int(cli.ScenarioExitCode.INVALID_INPUT)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        _emit_scenario_internal_error(
            output_format=format,
            scenario_id=scenario_id,
            scenario_document=scenario_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        raise typer.Exit(code=int(cli.ScenarioExitCode.INTERNAL_ERROR)) from exc
