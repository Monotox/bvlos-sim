"""Typer CLI adapter for estimator execution."""

import signal
from pathlib import Path
from types import FrameType
from typing import NoReturn

import typer

from adapters.version import tool_version

from adapters.cli_contract import __all__ as _contract_all
from adapters.cli_contract import (  # noqa: F401
    BatterySizingOutputFormat,
    CliExitCode,
    DocumentOutputFormat,
    PreflightFormat,
    ProgressFormat,
    ScenarioExitCode,
    SoraOutputFormat,
    SummaryOutputFormat,
    VerifyExitCode,
    _document_output_format,
    _exit_with_cli_error,
    _render_cli_error,
    _summary_output_format,
)

__all__ = [*_contract_all, "app", "install_cancellation_handlers"]

app = typer.Typer(name="bvlos-sim", add_completion=False, no_args_is_help=True)

def _handle_cancellation_signal(signum: int, _frame: FrameType | None) -> NoReturn:
    """Exit with the documented CANCELLED code on SIGTERM/SIGINT.

    Atomic output writes (Ticket 104) guarantee no partial ``--output`` file is
    left behind. A signal delivered after the atomic replacement may leave the
    new, complete artifact committed; this turns an interrupt into a defined exit code instead of
    the shell's default (``143`` for SIGTERM, ``130`` for SIGINT) so a backend
    worker can branch on it. ``raise SystemExit`` unwinds the stack, running
    ``finally`` blocks and context managers.
    """
    raise SystemExit(int(CliExitCode.CANCELLED))


def install_cancellation_handlers() -> None:
    """Route SIGTERM and SIGINT to the CANCELLED exit code.

    Called from the console-script entrypoint, not at import, so the in-process
    Typer test runner keeps Python's default ``KeyboardInterrupt`` behaviour.
    """
    signal.signal(signal.SIGTERM, _handle_cancellation_signal)
    signal.signal(signal.SIGINT, _handle_cancellation_signal)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bvlos-sim {tool_version()}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """BVLOS simulator command group."""


def _register_commands() -> None:
    from adapters.commands.batch import batch
    from adapters.commands.calibrate import calibrate
    from adapters.commands.compare import compare
    from adapters.commands.convert import convert
    from adapters.commands.estimate import estimate
    from adapters.commands.export import export
    from adapters.commands.ingest_log import ingest_log
    from adapters.commands.migrate import migrate
    from adapters.commands.propagate import propagate
    from adapters.commands.sample import sample
    from adapters.commands.scenario import scenario
    from adapters.commands.schema_versions import schema_versions
    from adapters.commands.sitl import sitl
    from adapters.commands.size_battery import size_battery
    from adapters.commands.sora import sora
    from adapters.commands.validate import validate
    from adapters.commands.verify_evidence import verify

    app.command()(convert)
    app.command()(estimate)
    app.command()(export)
    app.command("ingest-log")(ingest_log)
    app.command()(migrate)
    app.command("size-battery")(size_battery)
    app.command()(batch)
    app.command()(compare)
    app.command()(scenario)
    app.command()(sample)
    app.command()(propagate)
    app.command()(sitl)
    app.command()(sora)
    app.command()(validate)
    app.command()(verify)
    app.command()(calibrate)
    source_root = Path(__file__).resolve().parent.parent
    if (source_root / "pyproject.toml").is_file() and (
        source_root / "CHANGELOG.md"
    ).is_file():
        from adapters.commands.bump import bump

        app.command()(bump)
    app.command("schema-versions")(schema_versions)
    app.command("contracts")(schema_versions)


_register_commands()
