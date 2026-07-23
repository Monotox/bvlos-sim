"""SORA pre-assessment command."""

from pathlib import Path

import typer

import adapters.cli as cli
from adapters.assets.geofence_geojson import GeofenceLoadError
from adapters.assets.landing_zone_geojson import LandingZoneLoadError
from adapters.assets.obstacle_geojson import ObstacleLoadError
from adapters.cli_support import (
    NO_CLOBBER_OPTION,
    MissionAssetBundle,
    OutputWriteError,
    _populate_mission_assets,
    _refuse_output_clobber,
    _write_output,
)
from adapters.io import InputDocument, InputLoadError, load_mission, load_vehicle
from adapters.preflight import (
    check_file,
    emit_preflight,
    is_json_format,
    mission_asset_checks,
)
from adapters.sora_envelope import build_sora_envelope, render_sora_envelope_json
from adapters.sora_markdown import render_sora_markdown
from estimator.core.enums import EstimateStatus, FailureKind
from estimator.execution.sora import build_sora_assessment
from schemas.sora import GrcMitigationCreditStatus

_FAILURE_KIND_EXIT_CODES = {
    FailureKind.INFEASIBLE: cli.CliExitCode.INFEASIBLE,
    FailureKind.UNSUPPORTED: cli.CliExitCode.UNSUPPORTED,
}


def _run_sora_preflight(*, mission: Path, vehicle: Path, as_json: bool) -> None:
    """Validate mission, vehicle, and referenced assets without assessing."""
    files = []
    text_lines = []

    mission_check, mission_result = check_file(
        role="mission", path_str=mission.name, loader=lambda: load_mission(mission)
    )
    files.append(mission_check)
    if mission_check.ok:
        text_lines.append(f"mission: {mission.name}: OK")

    vehicle_check, _ = check_file(
        role="vehicle", path_str=vehicle.name, loader=lambda: load_vehicle(vehicle)
    )
    files.append(vehicle_check)
    if vehicle_check.ok:
        text_lines.append(f"vehicle: {vehicle.name}: OK")

    if mission_result is not None:
        files.extend(mission_asset_checks(mission_result[0], mission_path=mission))

    emit_preflight(
        command="sora", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def sora(
    mission: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to mission.v7 YAML file.",
    ),
    vehicle: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to vehicle profile YAML file.",
    ),
    format: cli.SoraOutputFormat = typer.Option(
        cli.SoraOutputFormat.MARKDOWN,
        "--format",
        help="Output format: markdown for the SORA report, json for the envelope.",
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to file instead of stdout."
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Validate mission and vehicle files (and referenced assets) against "
            "their schemas and exit without running the pre-assessment."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Run the SORA pre-assessment (Ground Risk, Air Risk, and SAIL)."""

    if validate_only:
        _run_sora_preflight(
            mission=mission, vehicle=vehicle, as_json=is_json_format(validate_format)
        )

    _refuse_output_clobber(output, no_clobber=no_clobber, command="sora")

    mission_document: InputDocument | None = None
    vehicle_document: InputDocument | None = None
    mission_assets = MissionAssetBundle()
    try:
        mission_model, mission_document = load_mission(mission)
        vehicle_model, vehicle_document = load_vehicle(vehicle)

        _populate_mission_assets(
            mission_assets,
            mission_model=mission_model,
            mission_document=mission_document,
        )
        result = cli.try_estimate_mission_distance_time(
            mission_model,
            vehicle_model,
            wind_provider=mission_assets.wind_provider,
            terrain_provider=mission_assets.terrain_provider,
            population_provider=mission_assets.population_provider,
            obstacle_provider=mission_assets.obstacle_provider,
            geofences=mission_assets.geofences,
            landing_zones=mission_assets.landing_zones,
        )
        if result.status != EstimateStatus.SUCCESS:
            failure = result.failure
            if failure is None:
                cli._exit_with_cli_error(
                    "Estimator failed without a structured failure.",
                    command="sora",
                    code=cli.CliExitCode.INTERNAL_ERROR,
                )
            assert failure is not None
            cli._exit_with_cli_error(
                failure.message,
                command="sora",
                code=_FAILURE_KIND_EXIT_CODES.get(
                    failure.kind, cli.CliExitCode.INVALID_INPUT
                ),
                details={
                    "failure_code": failure.code.value,
                    "failure_kind": failure.kind.value,
                    **failure.context,
                },
            )
        assessment = build_sora_assessment(
            mission_model,
            vehicle_model,
            result,
            population_evidence=getattr(
                mission_assets.population_provider, "sora_evidence", None
            ),
            terrain_provider=mission_assets.terrain_provider,
        )
        envelope = build_sora_envelope(
            result=assessment,
            mission_document=mission_document,
            vehicle_document=vehicle_document,
            population_document=mission_assets.population_document,
        )
        if format == cli.SoraOutputFormat.JSON:
            rendered = render_sora_envelope_json(envelope)
        else:
            rendered = render_sora_markdown(envelope)
        _write_output(rendered, output)
        mitigation_credit_rejected = any(
            credit.credit_status
            is GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B
            for credit in assessment.ground_risk_mitigations
        )
        exit_code = (
            cli.CliExitCode.SUCCESS
            if (
                assessment.within_specific_category_method_scope
                and not mitigation_credit_rejected
            )
            else cli.CliExitCode.INFEASIBLE
        )
        raise typer.Exit(code=int(exit_code))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INVALID_INPUT,
            details={"input_name": exc.input_name, "stage": str(exc.stage)},
        )
    except (GeofenceLoadError, LandingZoneLoadError, ObstacleLoadError) as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError:
        cli._exit_with_cli_error(
            "Failed to write SORA output.",
            command="sora",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except ValueError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="sora",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
