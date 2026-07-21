"""JARUS SORA 2.5 Air Risk Class (ARC) assignment.

The initial ARC follows the generalised Airspace Encounter Class table.  This
module deliberately does not turn a mitigation declaration into an ARC credit:
strategic reductions require local encounter-rate evidence, while tactical
mitigations satisfy the TMPR derived from the residual ARC without lowering it.
"""

from dataclasses import dataclass

from schemas.mission import Airspace, IcaoAirspaceClass
from schemas.sora import (
    DEFAULT_SORA_VERSION,
    AirRiskClass,
    GroundRiskMitigation,
    MitigationRobustness,
)

_LOW_ALTITUDE_CEILING_M = 152.4
_CONTROLLED_CLASSES = frozenset(
    {
        IcaoAirspaceClass.A,
        IcaoAirspaceClass.B,
        IcaoAirspaceClass.C,
        IcaoAirspaceClass.D,
        IcaoAirspaceClass.E,
    }
)
_AERODROME_ARC_D_CLASSES = frozenset(
    {IcaoAirspaceClass.B, IcaoAirspaceClass.C, IcaoAirspaceClass.D}
)
_AERODROME_ARC_C_CLASSES = frozenset(
    {
        IcaoAirspaceClass.A,
        IcaoAirspaceClass.E,
        IcaoAirspaceClass.F,
        IcaoAirspaceClass.G,
    }
)
_TMPR_BY_ARC = {
    AirRiskClass.A: MitigationRobustness.NONE,
    AirRiskClass.B: MitigationRobustness.LOW,
    AirRiskClass.C: MitigationRobustness.MEDIUM,
    AirRiskClass.D: MitigationRobustness.HIGH,
}


@dataclass(frozen=True, slots=True)
class AirRiskAssessment:
    initial_arc: AirRiskClass
    residual_arc: AirRiskClass
    strategic_mitigation_applied: bool
    tmpr_required_robustness: MitigationRobustness
    rationale: str


def _is_controlled(airspace_class: IcaoAirspaceClass) -> bool:
    return airspace_class in _CONTROLLED_CLASSES


def initial_air_risk_class(airspace: Airspace) -> tuple[AirRiskClass, str]:
    """Assign the SORA 2.5 initial ARC from the generalised AEC table."""

    if airspace.atypical_or_segregated:
        raise ValueError(
            "atypical_or_segregated ARC-a assignment is unsupported until an "
            "authority-backed atypical-airspace evidence workflow is implemented"
        )
    if airspace.entirely_above_flight_level_600:
        raise ValueError(
            "entirely_above_flight_level_600 assignment is unsupported until a "
            "pressure-altitude evidence workflow is implemented"
        )
    if airspace.aerodrome_environment:
        if airspace.airspace_class in _AERODROME_ARC_D_CLASSES:
            return (
                AirRiskClass.D,
                "airport/heliport environment in Class B, C, or D airspace",
            )
        if airspace.airspace_class in _AERODROME_ARC_C_CLASSES:
            return (
                AirRiskClass.C,
                "airport/heliport environment outside Class B, C, or D airspace",
            )
        raise AssertionError("unhandled ICAO airspace class")

    # The AEC table does not define equality at 500 ft. Assign the higher-risk
    # branch at the boundary instead of silently treating it as below 500 ft.
    above_500_ft = airspace.max_altitude_agl_m >= _LOW_ALTITUDE_CEILING_M
    if airspace.transponder_mandatory_zone:
        if above_500_ft:
            return AirRiskClass.D, "above 500 ft AGL in a Mode-C veil or TMZ"
        return AirRiskClass.C, "at or below 500 ft AGL in a Mode-C veil or TMZ"

    controlled = _is_controlled(airspace.airspace_class)
    if above_500_ft:
        if controlled:
            return AirRiskClass.D, "above 500 ft AGL in controlled airspace"
        return AirRiskClass.C, "above 500 ft AGL in uncontrolled airspace"
    if controlled:
        return AirRiskClass.C, "at or below 500 ft AGL in controlled airspace"
    if airspace.over_urban_area is None:
        raise ValueError(
            "over_urban_area is required to distinguish ARC-b from ARC-c for "
            "uncontrolled operations at or below 500 ft AGL"
        )
    if airspace.over_urban_area:
        return (
            AirRiskClass.C,
            "at or below 500 ft AGL in uncontrolled airspace over an urban area",
        )
    return (
        AirRiskClass.B,
        "at or below 500 ft AGL in uncontrolled airspace over a rural area",
    )


def compute_air_risk(
    airspace: Airspace,
    *,
    tactical: GroundRiskMitigation | None = None,
    sora_version: str = DEFAULT_SORA_VERSION,
) -> AirRiskAssessment:
    """Compute initial/residual ARC and the resulting TMPR requirement.

    Residual ARC equals initial ARC until an evidence-backed strategic
    assessment is implemented. Tactical mitigations never lower the ARC.
    """

    if sora_version != DEFAULT_SORA_VERSION:
        raise ValueError(
            f"unsupported SORA version {sora_version!r}; supported version is "
            f"{DEFAULT_SORA_VERSION!r}"
        )
    if airspace.strategic_mitigation:
        raise ValueError(
            "strategic ARC mitigation requires local encounter-rate evidence; "
            "a boolean declaration cannot be credited"
        )
    if tactical is not None and tactical.applied:
        raise ValueError(
            "tactical mitigation fulfils TMPR and cannot be used to lower residual ARC"
        )

    initial_arc, rationale = initial_air_risk_class(airspace)
    return AirRiskAssessment(
        initial_arc=initial_arc,
        residual_arc=initial_arc,
        strategic_mitigation_applied=False,
        tmpr_required_robustness=_TMPR_BY_ARC[initial_arc],
        rationale=rationale,
    )


__all__ = [
    "AirRiskAssessment",
    "compute_air_risk",
    "initial_air_risk_class",
]
