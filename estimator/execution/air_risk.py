"""SORA Air Risk Class (ARC) rule set.

The ARC categorises the likelihood of encountering manned aircraft in the
operational volume. This module implements a deterministic, table-driven
approximation of the SORA generalised airspace categorisation. It is a planning
aid, not a certified determination.
"""

from dataclasses import dataclass

from schemas.mission import Airspace, IcaoAirspaceClass
from schemas.sora import AirRiskClass, GroundRiskMitigation, MitigationRobustness

_R = MitigationRobustness

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

# Number of ARC bands a tactical air-risk mitigation (e.g. DAA) reduces, by
# robustness and SORA version. A simplified Tactical Mitigation Performance
# Requirement (TMPR) approximation, not a certified DAA credit.
_TACTICAL_ARC_REDUCTION: dict[str, dict[MitigationRobustness, int]] = {
    "2.0": {_R.NONE: 0, _R.LOW: 0, _R.MEDIUM: 1, _R.HIGH: 2},
}


@dataclass(frozen=True, slots=True)
class AirRiskAssessment:
    initial_arc: AirRiskClass
    residual_arc: AirRiskClass
    strategic_mitigation_applied: bool
    tactical_robustness: MitigationRobustness
    tactical_bands_reduced: int
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


def _lower_bands(arc: AirRiskClass, bands: int) -> AirRiskClass:
    index = _ARC_ORDER.index(arc)
    return _ARC_ORDER[max(index - bands, 0)]


def _tactical_bands(
    tactical: GroundRiskMitigation | None,
    *,
    sora_version: str,
) -> tuple[MitigationRobustness, int]:
    if tactical is None or not tactical.applied:
        return MitigationRobustness.NONE, 0
    table = _TACTICAL_ARC_REDUCTION.get(sora_version)
    if table is None:
        return tactical.robustness, 0
    return tactical.robustness, table[tactical.robustness]


def compute_air_risk(
    airspace: Airspace,
    *,
    tactical: GroundRiskMitigation | None = None,
    sora_version: str = "2.0",
) -> AirRiskAssessment:
    """Compute the initial and residual ARC for an airspace descriptor.

    The residual ARC is lowered first by the one-band strategic reduction (when
    declared on the airspace) and then by the declared tactical mitigation,
    floored at ARC-a.
    """
    initial_arc, rationale = initial_air_risk_class(airspace)

    strategic_applied = airspace.strategic_mitigation and initial_arc != AirRiskClass.A
    residual_arc = _lower_bands(initial_arc, 1) if strategic_applied else initial_arc

    tactical_robustness, tactical_bands = _tactical_bands(
        tactical, sora_version=sora_version
    )
    if tactical_bands > 0:
        residual_arc = _lower_bands(residual_arc, tactical_bands)

    return AirRiskAssessment(
        initial_arc=initial_arc,
        residual_arc=residual_arc,
        strategic_mitigation_applied=strategic_applied,
        tactical_robustness=tactical_robustness,
        tactical_bands_reduced=tactical_bands,
        rationale=rationale,
    )


__all__ = [
    "AirRiskAssessment",
    "compute_air_risk",
    "initial_air_risk_class",
]
