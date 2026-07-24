"""QGroundControl plan conversion command.

Conversion is fail-closed: any loss (dropped item, unsupported altitude frame,
or a populated ``geoFence``/``rallyPoints`` section) exits ``UNSUPPORTED`` (12)
without writing output unless ``--allow-lossy`` is passed. With
``--allow-lossy`` every loss is still reported on stderr and the run ends with
a one-line ``lossy conversion`` summary so CI logs show what was dropped.
"""

import json
from pathlib import Path

import typer
import yaml

import bvlos_sim.adapters.cli_contract as cli
from bvlos_sim.adapters.cli_support import (
    NO_CLOBBER_OPTION,
    OutputWriteError,
    _refuse_output_clobber,
    _write_output,
)
from bvlos_sim.adapters.preflight import check_file, emit_preflight, is_json_format
from bvlos_sim.adapters.qgc_plan import ConvertDiagnostic, load_and_convert_plan

_ALLOW_LOSSY_HINT = "Re-run with --allow-lossy to convert what can be converted."


def _diagnostic_scope(diagnostic: ConvertDiagnostic) -> str:
    if diagnostic.section is not None:
        return f"section {diagnostic.section}"
    return f"item {diagnostic.item_index} (command {diagnostic.command})"


def _lossy_summary(losses: list[ConvertDiagnostic]) -> str:
    dropped = sum(1 for diagnostic in losses if diagnostic.section is None)
    sections = [
        diagnostic.section for diagnostic in losses if diagnostic.section is not None
    ]
    line = f"lossy conversion: {dropped} item(s) dropped"
    if sections:
        line += ", sections: " + ", ".join(sections)
    return line


def _report_diagnostics(
    diagnostics: list[ConvertDiagnostic], *, allow_lossy: bool
) -> None:
    """Print conversion diagnostics to stderr, failing closed on losses.

    Without ``allow_lossy`` any loss lists every dropped item and section,
    prints the summary, and exits ``UNSUPPORTED`` (12) before output is
    written. With ``allow_lossy`` losses are downgraded to warnings and the
    one-line summary still ends the diagnostic block.
    """
    losses = [diagnostic for diagnostic in diagnostics if diagnostic.lossy]
    if losses and not allow_lossy:
        for diagnostic in diagnostics:
            prefix = "Error" if diagnostic.lossy else "Warning"
            typer.echo(
                f"{prefix}: {_diagnostic_scope(diagnostic)}: {diagnostic.message}",
                err=True,
            )
        typer.echo(
            f"Error: {_lossy_summary(losses)}; no output written. "
            f"{_ALLOW_LOSSY_HINT}",
            err=True,
        )
        raise typer.Exit(code=int(cli.CliExitCode.UNSUPPORTED))
    for diagnostic in diagnostics:
        typer.echo(
            f"Warning: {_diagnostic_scope(diagnostic)}: {diagnostic.message}",
            err=True,
        )
    if losses:
        typer.echo(_lossy_summary(losses), err=True)


def _run_convert_preflight(
    *, plan: Path, vehicle_profile: str, as_json: bool, allow_lossy: bool
) -> None:
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
        _report_diagnostics(diagnostics, allow_lossy=allow_lossy)
        route_items = len(mission.get("route", []))
        text_lines.append(f"plan: {plan.name}: OK ({route_items} route items)")

    emit_preflight(
        command="convert", files=files, as_json=as_json, text_ok_lines=text_lines
    )


def convert(
    plan: Path = typer.Argument(..., resolve_path=True),
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
    allow_lossy: bool = typer.Option(
        False,
        "--allow-lossy",
        help=(
            "Convert what can be converted even when the .plan contains "
            "unsupported items or geoFence/rallyPoints data. Every loss is "
            "still reported on stderr and the run ends with a one-line "
            "'lossy conversion' summary. Without this flag any loss exits "
            "UNSUPPORTED (12) and nothing is written."
        ),
    ),
    no_clobber: bool = NO_CLOBBER_OPTION,
    validate_only: bool = typer.Option(
        False,
        "--validate-only",
        help=(
            "Parse and validate the .plan file without writing output. "
            "Exits 0 when the file is valid and losslessly convertible, "
            "UNSUPPORTED when conversion would be lossy (unless --allow-lossy), "
            "INVALID_INPUT otherwise."
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
            allow_lossy=allow_lossy,
        )

    _refuse_output_clobber(output, no_clobber=no_clobber, command="convert")

    try:
        mission, diagnostics = load_and_convert_plan(
            plan, vehicle_profile=vehicle_profile.strip()
        )
        _report_diagnostics(diagnostics, allow_lossy=allow_lossy)
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
