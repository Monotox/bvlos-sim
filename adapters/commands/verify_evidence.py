"""SITL evidence checksum verification command."""

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

import typer

import adapters.cli_contract as cli
from adapters.io import InputLoadError
from adapters.sitl.evidence_io import load_sitl_evidence_bundle
from schemas import SitlArtifactReference, SitlEvidenceBundle

_READ_CHUNK_BYTES = 1 << 20


class ArtifactCheckStatus(StrEnum):
    OK = "OK"
    MISMATCH = "MISMATCH"
    MISSING = "MISSING"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class ArtifactCheck:
    """Outcome of re-verifying one recorded artifact checksum."""

    status: ArtifactCheckStatus
    role: str
    path: str
    note: str | None = None


def _bundle_artifact_references(
    bundle: SitlEvidenceBundle,
) -> list[SitlArtifactReference]:
    return [
        *bundle.inputs,
        *bundle.expected.reports,
        *bundle.observed.telemetry,
        *bundle.observed.command_logs,
        *bundle.observed.simulator_logs,
        *bundle.observed.adapter_logs,
    ]


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _check_artifact(reference: SitlArtifactReference) -> ArtifactCheck:
    role = reference.role.value
    if reference.sha256 is None:
        return ArtifactCheck(
            status=ArtifactCheckStatus.SKIPPED,
            role=role,
            path=reference.path,
            note="no recorded sha256",
        )
    # load_sitl_evidence_bundle already resolved relative paths against the
    # bundle file's directory; URI references cannot be re-read locally.
    artifact_path = Path(reference.path)
    try:
        computed = _file_sha256(artifact_path)
    except OSError as exc:
        return ArtifactCheck(
            status=ArtifactCheckStatus.MISSING,
            role=role,
            path=reference.path,
            note=f"unreadable artifact file ({type(exc).__name__})",
        )
    if computed != reference.sha256.lower():
        return ArtifactCheck(
            status=ArtifactCheckStatus.MISMATCH,
            role=role,
            path=reference.path,
            note=f"recorded {reference.sha256.lower()}, computed {computed}",
        )
    return ArtifactCheck(status=ArtifactCheckStatus.OK, role=role, path=reference.path)


def _render_check_line(check: ArtifactCheck) -> str:
    line = f"{check.status.value:<8} {check.role:<15} {check.path}"
    if check.note is not None:
        line += f" ({check.note})"
    return line


def _render_verdict(checks: list[ArtifactCheck]) -> tuple[str, cli.VerifyExitCode]:
    counts = {
        status: sum(1 for check in checks if check.status is status)
        for status in ArtifactCheckStatus
    }
    failed = (
        counts[ArtifactCheckStatus.MISMATCH] + counts[ArtifactCheckStatus.MISSING]
    )
    summary = (
        f"{counts[ArtifactCheckStatus.OK]} ok, "
        f"{counts[ArtifactCheckStatus.MISMATCH]} mismatch, "
        f"{counts[ArtifactCheckStatus.MISSING]} missing, "
        f"{counts[ArtifactCheckStatus.SKIPPED]} skipped"
    )
    if failed:
        return f"verify: FAIL ({summary})", cli.VerifyExitCode.FAILED
    return f"verify: PASS ({summary})", cli.VerifyExitCode.PASSED


def verify(
    evidence: Path = typer.Argument(
        ...,
        help="Path to a sitl-evidence.v1 JSON or YAML bundle.",
    ),
) -> None:
    """Re-verify the recorded artifact checksums of a SITL evidence bundle.

    Loads the bundle, recomputes the SHA-256 of every referenced artifact file
    (relative artifact paths resolve against the bundle file's directory), and
    compares each digest against the checksum recorded in the bundle. One line
    is printed per artifact — OK, MISMATCH, MISSING (file absent or
    unreadable), or SKIPPED when the reference carries no recorded sha256 —
    followed by a final verdict line. Exits 0 when every recorded checksum
    matches, 10 on any mismatch or missing artifact, and 11 when the bundle
    itself is unreadable or fails schema validation.
    """

    try:
        bundle, _document = load_sitl_evidence_bundle(evidence)
        checks = [
            _check_artifact(reference)
            for reference in _bundle_artifact_references(bundle)
        ]
        for check in checks:
            typer.echo(_render_check_line(check))
        verdict, exit_code = _render_verdict(checks)
        typer.echo(verdict)
        raise typer.Exit(code=int(exit_code))
    except InputLoadError as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="verify",
            code=cli.CliExitCode.INVALID_INPUT,
            details=exc.to_context(),
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli._exit_with_cli_error(
            str(exc),
            command="verify",
            code=cli.CliExitCode.INTERNAL_ERROR,
        )
