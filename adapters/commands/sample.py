"""Monte Carlo uncertainty sample command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.cli_support import (
    NO_CLOBBER_OPTION,
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _refuse_output_clobber,
    _render_uncertainty_output,
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
from adapters.uncertainty_envelope import build_uncertainty_envelope
from adapters.uncertainty_io import (
    load_uncertainty_plan,
    resolve_uncertainty_asset_path,
)


def _run_sample_preflight(*, uncertainty_file: Path, as_json: bool) -> None:
    """Validate uncertainty, mission, vehicle, and assets without sampling."""
    files = []
    text_lines = []

    plan_check, plan_loaded = check_file(
        role="uncertainty",
        path_str=uncertainty_file.name,
        loader=lambda: load_uncertainty_plan(uncertainty_file),
    )
    files.append(plan_check)
    if plan_check.ok and plan_loaded is not None:
        text_lines.append(f"uncertainty: {uncertainty_file.name}: OK")
        plan = plan_loaded[0]
        mission_path = resolve_uncertainty_asset_path(
            plan.mission_file, uncertainty_path=uncertainty_file
        )
        vehicle_path = resolve_uncertainty_asset_path(
            plan.vehicle_file, uncertainty_path=uncertainty_file
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
        command="sample", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def sample(
    uncertainty_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to uncertainty.v2 diagnostic YAML file.",
    ),
    format: cli.SummaryOutputFormat = typer.Option(
        cli.SummaryOutputFormat.JSON,
        "--format",
        help=(
            "Output format. Summary reports a diagnostic modeled-pass rate and "
            "conditional mission-end energy distribution."
        ),
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
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
            "Validate uncertainty, mission, and vehicle files (and referenced "
            "assets) against their schemas and exit without running the sampler. "
            "Exits 0 when all files are valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Run a diagnostic parameter sweep and emit uncertainty-report.v2."""

    if validate_only:
        _run_sample_preflight(
            uncertainty_file=uncertainty_file,
            as_json=is_json_format(validate_format),
        )

    _refuse_output_clobber(output, no_clobber=no_clobber, command="sample")

    uncertainty_document = None
    mission_document = None
    vehicle_document = None
    mission_assets = MissionAssetBundle()

    try:
        plan, uncertainty_document = load_uncertainty_plan(uncertainty_file)

        mission_path = resolve_uncertainty_asset_path(
            plan.mission_file, uncertainty_path=uncertainty_file
        )
        vehicle_path = resolve_uncertainty_asset_path(
            plan.vehicle_file, uncertainty_path=uncertainty_file
        )

        mission_model, mission_document = load_mission(mission_path)
        vehicle_model, vehicle_document = load_vehicle(vehicle_path)

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )

        with progress_reporter(
            "sample",
            enabled=progress_format is cli.ProgressFormat.JSONL,
            progress_file=progress_file,
            protected_paths=(
                uncertainty_file,
                mission_path,
                vehicle_path,
                output,
                *(doc.path for doc in mission_assets.known_documents().values() if doc),
            ),
        ) as reporter:
            result = cli.run_monte_carlo(
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
        envelope = build_uncertainty_envelope(
            result=result,
            uncertainty_document=uncertainty_document,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
        )
        _write_output(
            _render_uncertainty_output(cli._summary_output_format(format), envelope),
            output,
        )
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sample",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
