"""SORA Air Risk Class (ARC) rule set.

The ARC categorises the likelihood of encountering manned aircraft in the
operational volume. This module implements a deterministic, table-driven
approximation of the SORA generalised airspace categorisation. It is a planning
aid, not a certified determination.
"""

from dataclasses import dataclass

from schemas.mission import Airspace, IcaoAirspaceClass
from schemas.sora import AirRiskClass

# 500 ft AGL, the SORA threshold separating low-altitude operations from the
# en-route / controlled airspace bands.
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

# Ascending collision-risk order; index used for the one-band strategic
# reduction.
_ARC_ORDER = (
    AirRiskClass.A,
    AirRiskClass.B,
    AirRiskClass.C,
    AirRiskClass.D,
)


@dataclass(frozen=True, slots=True)
class AirRiskAssessment:
    initial_arc: AirRiskClass
    residual_arc: AirRiskClass
    strategic_mitigation_applied: bool
    rationale: str


def _is_controlled(airspace_class: IcaoAirspaceClass) -> bool:
    return airspace_class in _CONTROLLED_CLASSES


def initial_air_risk_class(airspace: Airspace) -> tuple[AirRiskClass, str]:
    """Assign the initial ARC from the airspace descriptor."""
    if airspace.atypical_or_segregated:
        return (
            AirRiskClass.A,
            "atypical or segregated volume where manned traffic is not expected",
        )
    if airspace.near_aerodrome:
        return (
            AirRiskClass.D,
            "operation within an aerodrome traffic zone",
        )

    controlled = _is_controlled(airspace.airspace_class)
    if airspace.max_altitude_agl_m > _LOW_ALTITUDE_CEILING_M:
        if controlled:
            return (
                AirRiskClass.D,
                "above 500 ft AGL in controlled airspace",
            )
        return (
            AirRiskClass.C,
            "above 500 ft AGL in uncontrolled airspace",
        )
    if controlled:
        return (
            AirRiskClass.C,
            "at or below 500 ft AGL in controlled airspace",
        )
    return (
        AirRiskClass.B,
        "at or below 500 ft AGL in uncontrolled airspace",
    )


def _lower_one_band(arc: AirRiskClass) -> AirRiskClass:
    index = _ARC_ORDER.index(arc)
    return _ARC_ORDER[max(index - 1, 0)]


def compute_air_risk(airspace: Airspace) -> AirRiskAssessment:
    """Compute the initial and residual ARC for an airspace descriptor."""
    initial_arc, rationale = initial_air_risk_class(airspace)

    applied = airspace.strategic_mitigation and initial_arc != AirRiskClass.A
    residual_arc = _lower_one_band(initial_arc) if applied else initial_arc
    return AirRiskAssessment(
        initial_arc=initial_arc,
        residual_arc=residual_arc,
        strategic_mitigation_applied=applied,
        rationale=rationale,
    )


__all__ = [
    "AirRiskAssessment",
    "compute_air_risk",
    "initial_air_risk_class",
]
