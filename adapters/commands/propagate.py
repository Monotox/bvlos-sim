"""Stochastic propagation command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import (
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _render_stochastic_output,
    _write_output,
)
from adapters.io import InputLoadError, load_mission, load_vehicle
from adapters.preflight import (
    check_file,
    emit_preflight,
    is_json_format,
    mission_asset_checks,
)
from adapters.progress import progress_reporter
from adapters.stochastic_envelope import build_stochastic_envelope
from adapters.stochastic_io import load_stochastic_plan, resolve_stochastic_asset_path


def _run_propagate_preflight(*, stochastic_file: Path, as_json: bool) -> None:
    """Validate stochastic, mission, vehicle, and assets without propagating."""
    files = []
    text_lines = []

    plan_check, plan_loaded = check_file(
        role="stochastic",
        path_str=stochastic_file.name,
        loader=lambda: load_stochastic_plan(stochastic_file),
    )
    files.append(plan_check)
    if plan_check.ok and plan_loaded is not None:
        text_lines.append(f"stochastic: {stochastic_file.name}: OK")
        plan = plan_loaded[0]
        mission_path = resolve_stochastic_asset_path(
            plan.mission_file, stochastic_path=stochastic_file
        )
        vehicle_path = resolve_stochastic_asset_path(
            plan.vehicle_file, stochastic_path=stochastic_file
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
        if mission_result is not None:
            files.extend(
                mission_asset_checks(mission_result[0], mission_path=mission_path)
            )

    emit_preflight(
        command="propagate", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def propagate(
    stochastic_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to stochastic.v1 YAML file.",
    ),
    format: cli.SummaryOutputFormat = typer.Option(
        cli.SummaryOutputFormat.JSON,
        "--format",
        help="Output format. Use summary for a one-line feasibility and reserve result.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    progress_format: cli.ProgressFormat = typer.Option(
        cli.ProgressFormat.NONE,
        "--progress-format",
        help="Emit machine-readable progress. Use jsonl for one JSON record per interval on stderr.",
    ),
    progress_file: Path | None = typer.Option(
        None,
        "--progress-file",
        help="Write JSONL progress to this file instead of stderr (implies --progress-format jsonl).",
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate stochastic, mission, and vehicle files (and referenced "
            "assets) against their schemas and exit without running propagation. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Run stochastic state propagation and emit a stochastic-envelope.v1 report."""

    if validate_only:
        _run_propagate_preflight(
            stochastic_file=stochastic_file,
            as_json=is_json_format(validate_format),
        )

    stochastic_document = None
    mission_document = None
    vehicle_document = None
    mission_assets = MissionAssetBundle()

    try:
        plan, stochastic_document = load_stochastic_plan(stochastic_file)

        mission_path = resolve_stochastic_asset_path(
            plan.mission_file, stochastic_path=stochastic_file
        )
        vehicle_path = resolve_stochastic_asset_path(
            plan.vehicle_file, stochastic_path=stochastic_file
        )

        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        with progress_reporter(
            "propagate",
            enabled=progress_format is cli.ProgressFormat.JSONL,
            progress_file=progress_file,
        ) as reporter:
            result = cli.run_stochastic_propagation(
                plan,
                mission_model,
                vehicle_model,
                wind_provider=mission_assets.wind_provider,
                terrain_provider=mission_assets.terrain_provider,
                population_provider=mission_assets.population_provider,
                obstacle_provider=mission_assets.obstacle_provider,
                geofences=mission_assets.geofences,
                landing_zones=mission_assets.landing_zones,
                progress=reporter,
            )
        envelope = build_stochastic_envelope(
            result=result,
            stochastic_document=stochastic_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        _write_output(
            _render_stochastic_output(cli._summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="propagate",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
