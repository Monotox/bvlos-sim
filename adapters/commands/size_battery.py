"""Battery sizing command."""

from collections.abc import Callable
from pathlib import Path

import typer

import adapters.cli as cli
from adapters.battery_sizer import (
    BatterySizingResult,
    compute_minimum_battery_capacity,
    render_battery_sizing_markdown,
    render_battery_sizing_summary,
)
from adapters.battery_sizing_envelope import (
    BatterySizingEnvelope,
    build_battery_sizing_envelope,
    render_battery_sizing_envelope_json,
)
from adapters.cli_support import MissionAssetBundle, OutputWriteError, _populate_mission_assets, _write_output
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.assets.terrain_grid import TerrainGridLoadError
from adapters.assets.wind_grid import WindGridLoadError


def _validate_battery_sizing_margins(
    margins: list[int] | None,
) -> list[int] | None:
    if margins is None:
        return None
    if any(margin < 0 for margin in margins):
        raise ValueError("--margin values must be non-negative.")
    return list(margins)


BatterySizingRenderer = Callable[
    [BatterySizingEnvelope, BatterySizingResult, str, list[int] | None], str
]


def _render_battery_sizing_json(
    envelope: BatterySizingEnvelope,
    _result: BatterySizingResult,
    _mission_id: str,
    _safety_margins: list[int] | None,
) -> str:
    return render_battery_sizing_envelope_json(envelope)


def _render_battery_sizing_markdown_output(
    _envelope: BatterySizingEnvelope,
    result: BatterySizingResult,
    mission_id: str,
    safety_margins: list[int] | None,
) -> str:
    return render_battery_sizing_markdown(
        result,
        mission_id=mission_id,
        safety_margins=safety_margins,
    )


def _render_battery_sizing_summary_output(
    _envelope: BatterySizingEnvelope,
    result: BatterySizingResult,
    _mission_id: str,
    safety_margins: list[int] | None,
) -> str:
    return render_battery_sizing_summary(
        result,
        safety_margins=safety_margins,
    )


_BATTERY_SIZING_RENDERERS: dict[
    cli.BatterySizingOutputFormat, BatterySizingRenderer
] = {
    cli.BatterySizingOutputFormat.JSON: _render_battery_sizing_json,
    cli.BatterySizingOutputFormat.MARKDOWN: _render_battery_sizing_markdown_output,
    cli.BatterySizingOutputFormat.SUMMARY: _render_battery_sizing_summary_output,
}


def _render_battery_sizing_command_output(
    output_format: cli.BatterySizingOutputFormat,
    envelope: BatterySizingEnvelope,
    result: BatterySizingResult,
    *,
    mission_id: str,
    safety_margins: list[int] | None,
) -> str:
    renderer = _BATTERY_SIZING_RENDERERS[output_format]
    return renderer(envelope, result, mission_id, safety_margins)


def size_battery(
    mission: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="Path to mission.v5 YAML file."),
    vehicle: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True, help="Path to vehicle profile YAML file."),
    format: cli.BatterySizingOutputFormat = typer.Option(
        cli.BatterySizingOutputFormat.MARKDOWN,
        "--format",
        help="Output format. Defaults to markdown for a human-readable sizing report.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write output to file instead of stdout."),
    margin: list[int] | None = typer.Option(
        None,
        "--margin",
        help="Safety margin percent. Repeat to show multiple recommendations.",
    ),
) -> None:
    """Compute minimum battery capacity needed for mission feasibility."""

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    try:
        safety_margins = _validate_battery_sizing_margins(margin)
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)
        mission_assets.mission_id = mission_model.mission_id
        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        envelope_inputs = mission_assets.envelope_inputs(
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        result = compute_minimum_battery_capacity(
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        mission_id = mission_assets.mission_id or mission.stem
        envelope = build_battery_sizing_envelope(
            result=result,
            mission_id=mission_id,
            inputs=envelope_inputs,
        )
        rendered = _render_battery_sizing_command_output(
            format,
            envelope,
            result,
            mission_id=mission_id,
            safety_margins=safety_margins,
        )
        _write_output(rendered, output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except (
        GeofenceLoadError,
        LandingZoneLoadError,
        TerrainGridLoadError,
        WindGridLoadError,
    ) as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="size-battery",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            "Unable to write size-battery output.",
            command="size-battery",
            code=cli.CliExitCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__},
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            "Unexpected internal error while running size-battery.",
            command="size-battery",
            code=cli.CliExitCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__},
        )
