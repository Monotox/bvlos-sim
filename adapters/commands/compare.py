"""SITL evidence comparison command."""

from pathlib import Path

import typer
from pydantic import ValidationError

import adapters.cli as cli
from adapters.cli_support import OutputWriteError, _write_output
from adapters.io import InputLoadError
from adapters.sitl.evidence import compare_sitl_evidence_bundle
from adapters.sitl.evidence_io import load_sitl_evidence_bundle
from adapters.cli_sitl_support import (
    _exit_code_for_comparison_report,
    _render_sitl_comparison_output,
)


def compare(
    evidence: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        resolve_path=True,
        help="Path to a sitl-evidence.v1 JSON bundle.",
    ),
    comparison_id: str | None = typer.Option(
        None,
        "--comparison-id",
        help="Stable comparison report identifier. Defaults to <evidence_id>-comparison.",
    ),
    position_tolerance_m: float = typer.Option(
        500.0,
        "--position-tolerance-m",
        min=0.0,
        help="Position proximity tolerance in metres.",
    ),
    format: cli.DocumentOutputFormat = typer.Option(
        cli.DocumentOutputFormat.JSON,
        "--format",
        help="Output format for the comparison report.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write output to file instead of stdout."),
) -> None:
    """Compare a SITL evidence bundle against its embedded scenario expectations."""

    try:
        bundle, _document = load_sitl_evidence_bundle(evidence)
        report = compare_sitl_evidence_bundle(
            bundle,
            comparison_id=comparison_id or f"{bundle.evidence_id}-comparison",
            position_tolerance_m=position_tolerance_m,
        )
        _write_output(
            _render_sitl_comparison_output(cli._document_output_format(format), report),
            output,
        )
        raise typer.Exit(code=int(_exit_code_for_comparison_report(report)))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="compare",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        cli._exit_with_cli_error(
            f"comparison_id: {first['msg']}",
            command="compare",
            code=cli.CliExitCode.INVALID_INPUT,
        )
    except OutputWriteError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="compare",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="compare",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
