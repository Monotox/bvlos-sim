"""Structured fail-closed operational readiness verdicts."""

from collections.abc import Iterable
from enum import StrEnum
import math

from pydantic import BaseModel, ConfigDict, Field

from bvlos_sim.estimator.core.results import MissionEstimate
from bvlos_sim.estimator.core.enums import EstimateStatus


class OperationalVerdict(StrEnum):
    GO = "go"
    NO_GO = "no_go"


class OperationalReadiness(BaseModel):
    """Machine-readable counterpart to pre-flight checklist status."""

    model_config = ConfigDict(extra="forbid")

    verdict: OperationalVerdict
    is_go: bool
    missing_evidence: list[str] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    acknowledged_warning_codes: list[str] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )


def evaluate_operational_readiness(
    result: MissionEstimate | None,
    *,
    additional_failed_checks: Iterable[str] = (),
    additional_missing_evidence: Iterable[str] = (),
) -> OperationalReadiness:
    """Evaluate all mandatory GO checks without depending on output rendering."""
    missing: list[str] = list(additional_missing_evidence)
    failed = list(additional_failed_checks)
    warning_codes: list[str] = []
    acknowledged: list[str] = []
    if result is None:
        missing.append("estimate")
    else:
        if result.status is not EstimateStatus.SUCCESS:
            failed.append("estimate_status")
        if result.failure is not None:
            failed.append("estimate")
        if result.totals_are_partial:
            failed.append("estimate_completeness")
        totals = (
            result.total_horizontal_distance_m,
            result.total_vertical_distance_m,
            result.total_path_distance_m,
            result.total_time_s,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in totals):
            failed.append("estimate_totals")
        if not result.legs:
            missing.append("route_legs")
        checks = (
            ("energy", result.energy),
            ("geofence", result.geofence),
            ("landing_zone", result.landing_zone),
            ("resource", result.resource),
            ("link", result.link),
            ("obstacle", result.obstacle),
            ("weather", result.weather),
        )
        for name, check in checks:
            if check is None:
                missing.append(name)
            elif not check.is_feasible:
                failed.append(name)
        if result.resource is not None and result.resource.selected_resource_id is None:
            failed.append("resource")
        elif result.resource is not None and not any(
            system.resource_id == result.resource.selected_resource_id
            and system.is_feasible
            for system in result.resource.systems
        ):
            failed.append("resource_coverage")
        if result.link is not None and result.link.selected_link_id is None:
            failed.append("link")
        elif result.link is not None and not any(
            system.link_id == result.link.selected_link_id and system.is_feasible
            for system in result.link.systems
        ):
            failed.append("link_coverage")
        if result.rth_is_feasible is None:
            missing.append("rth")
        elif not result.rth_is_feasible:
            failed.append("rth")
        if result.ground_risk is None:
            missing.append("ground_risk")
        elif result.ground_risk.population_assessment_buffer_m <= 0.0:
            # Density sampled along the route centerline says nothing about the
            # operational volume, and can report a lower iGRC than the buffered
            # assessment of the same route. It is a diagnostic, not evidence.
            missing.append("ground_risk_footprint")
        elif result.ground_risk.mission_igrc > 7:
            failed.append("ground_risk")
        if result.legs:
            expected_leg_indices = {leg.leg_index for leg in result.legs}
            if (
                result.energy is not None
                and {leg.leg_index for leg in result.energy.legs}
                != expected_leg_indices
            ):
                failed.append("energy_coverage")
            count_checks = (
                ("geofence", result.geofence),
                ("obstacle", result.obstacle),
                ("weather", result.weather),
            )
            for name, check in count_checks:
                if check is not None and check.checked_leg_count != len(result.legs):
                    failed.append(f"{name}_coverage")
            if (
                result.ground_risk is not None
                and {leg.leg_index for leg in result.ground_risk.legs}
                != expected_leg_indices
            ):
                failed.append("ground_risk_coverage")
        if result.landing_zone is not None and (
            result.landing_zone.checked_state_count == 0
            or result.landing_zone.checked_state_count
            != len(result.landing_zone.states)
        ):
            failed.append("landing_zone_coverage")
        warning_codes = [str(warning.code) for warning in result.warnings]
        accepted = _accepted_warning_codes(result)
        acknowledged = sorted({code for code in warning_codes if code in accepted})
        if any(code not in accepted for code in warning_codes):
            failed.append("warnings")

    missing = list(dict.fromkeys(missing))
    failed = list(dict.fromkeys(failed))
    is_go = not missing and not failed
    return OperationalReadiness(
        verdict=OperationalVerdict.GO if is_go else OperationalVerdict.NO_GO,
        is_go=is_go,
        missing_evidence=missing,
        failed_checks=failed,
        warning_codes=warning_codes,
        acknowledged_warning_codes=acknowledged,
    )


def _accepted_warning_codes(result: MissionEstimate) -> frozenset[str]:
    """Warning codes the mission explicitly accepted, from result metadata."""
    raw = result.metadata.get("accepted_warning_codes")
    if not isinstance(raw, str) or not raw:
        return frozenset()
    return frozenset(raw.split(","))


__all__ = [
    "OperationalReadiness",
    "OperationalVerdict",
    "evaluate_operational_readiness",
]
