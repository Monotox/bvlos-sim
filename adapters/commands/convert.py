"""QGroundControl plan conversion command."""

import json
from pathlib import Path

import typer
import yaml

import adapters.cli as cli
from adapters.cli_support import OutputWriteError, _write_output
from adapters.preflight import check_file, emit_preflight, is_json_format
from adapters.qgc_plan import load_and_convert_plan


def _run_convert_preflight(*, plan: Path, vehicle_profile: str, as_json: bool) -> None:
    """Validate and convert a .plan file in memory without writing output."""
    files = []
    text_lines = []

    check, loaded = check_file(
        role="plan",
        path_str=plan.name,
        loader=lambda: load_and_convert_plan(plan, vehicle_profile=vehicle_profile),
    )
    files.append(check)
    if check.ok and loaded is not None:
        mission, diagnostics = loaded
        for diagnostic in diagnostics:
            typer.echo(
                "Warning: item "
                f"{diagnostic.item_index} (command {diagnostic.command}): "
                f"{diagnostic.message}",
                err=True,
            )
        route_items = len(mission.get("route", []))
        text_lines.append(f"plan: {plan.name}: OK ({route_items} route items)")

    emit_preflight(
        command="convert", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def convert(
    plan: Path = typer.Argument(..., exists=True, readable=True, resolve_path=True),
    vehicle_profile: str | None = typer.Option(
        None,
        "--vehicle-profile",
        help=(
            "Vehicle profile id to write into the converted mission YAML. "
            "Must match the vehicle_id in the vehicle profile YAML you intend to use. "
            "Required."
        ),
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write converted YAML to file instead of stdout."
    ),
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Parse and validate the .plan file without writing output. "
            "Exits 0 when the file is valid, INVALID_INPUT otherwise."
        ),
    ),
    validate_format: cli.PreflightFormat = typer.Option(
        cli.PreflightFormat.TEXT,
        "--validate-format",
        help="Validate-only output: text (default) or json for a preflight-validation.v1 envelope.",
    ),
) -> None:
    """Convert a QGroundControl .plan file to a mission.v7 YAML."""

    if not vehicle_profile or not vehicle_profile.strip():
        typer.echo(
            "Error: --vehicle-profile is required. "
            "Pass the vehicle_id from the vehicle profile you intend to use, "
            "e.g. --vehicle-profile quadplane_v1",
            err=True,
        )
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT))

    if validate_only:
        _run_convert_preflight(
            plan=plan,
            vehicle_profile=vehicle_profile.strip(),
            as_json=is_json_format(validate_format),
        )

    try:
        mission, diagnostics = load_and_convert_plan(
            plan, vehicle_profile=vehicle_profile.strip()
        )
        for diagnostic in diagnostics:
            typer.echo(
                "Warning: item "
                f"{diagnostic.item_index} (command {diagnostic.command}): "
                f"{diagnostic.message}",
                err=True,
            )
        rendered = yaml.dump(
            mission,
            default_flow_style=False,
            sort_keys=False,
        )
        _write_output(rendered, output)
        raise typer.Exit(code=int(cli.CliExitCode.SUCCESS))
    except (json.JSONDecodeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INVALID_INPUT)) from exc
    except OutputWriteError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=int(cli.CliExitCode.INTERNAL_ERROR)) from exc
