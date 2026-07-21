"""SORA SAIL determination and Operational Safety Objective (OSO) assignment.

The SAIL is looked up from the final Ground Risk Class and the residual Air Risk
Class. The applicable OSOs and their required robustness are a static function of
the SAIL.

The matrices below transcribe the JARUS SORA 2.5 SAIL determination table
(main body, Table 7) and the OSO robustness assignment table (Table 14). They are kept as
single auditable constants; verify any cell against the official annex before
relying on it. Robustness levels: NR (not required), L (low), M (medium), H (high).
"""

from schemas.sora import (
    AirRiskClass,
    OsoPartyDependencies,
    OsoPartyDependency,
    OsoRequirement,
    RobustnessLevel,
    Sail,
)

_NR = RobustnessLevel.NOT_REQUIRED
_L = RobustnessLevel.LOW
_M = RobustnessLevel.MEDIUM
_H = RobustnessLevel.HIGH

_MAX_SPECIFIC_CATEGORY_GRC = 7

# Final GRC (1..7) x residual ARC -> SAIL. SORA 2.5 Main Body, Table 7.
_SAIL_MATRIX: dict[int, dict[AirRiskClass, Sail]] = {
    1: {
        AirRiskClass.A: Sail.I,
        AirRiskClass.B: Sail.II,
        AirRiskClass.C: Sail.IV,
        AirRiskClass.D: Sail.VI,
    },
    2: {
        AirRiskClass.A: Sail.I,
        AirRiskClass.B: Sail.II,
        AirRiskClass.C: Sail.IV,
        AirRiskClass.D: Sail.VI,
    },
    3: {
        AirRiskClass.A: Sail.II,
        AirRiskClass.B: Sail.II,
        AirRiskClass.C: Sail.IV,
        AirRiskClass.D: Sail.VI,
    },
    4: {
        AirRiskClass.A: Sail.III,
        AirRiskClass.B: Sail.III,
        AirRiskClass.C: Sail.IV,
        AirRiskClass.D: Sail.VI,
    },
    5: {
        AirRiskClass.A: Sail.IV,
        AirRiskClass.B: Sail.IV,
        AirRiskClass.C: Sail.IV,
        AirRiskClass.D: Sail.VI,
    },
    6: {
        AirRiskClass.A: Sail.V,
        AirRiskClass.B: Sail.V,
        AirRiskClass.C: Sail.V,
        AirRiskClass.D: Sail.VI,
    },
    7: {
        AirRiskClass.A: Sail.VI,
        AirRiskClass.B: Sail.VI,
        AirRiskClass.C: Sail.VI,
        AirRiskClass.D: Sail.VI,
    },
}

# SAIL ordering used to index the per-OSO robustness tuples below.
_SAIL_COLUMN_ORDER = (Sail.I, Sail.II, Sail.III, Sail.IV, Sail.V, Sail.VI)

# Party dependency representation from Table 14: ``None`` is a dash (no
# dependency), ``()`` is a plain X, and a non-empty tuple carries the numbered
# criterion references printed in the table. Order is operator, training
# organisation, designer.
type _PartyCriterionRefs = tuple[int, ...] | None
type _PartyDependencies = tuple[
    _PartyCriterionRefs,
    _PartyCriterionRefs,
    _PartyCriterionRefs,
]
_X: tuple[int, ...] = ()
_DASH = None

# (OSO id, title, robustness per SAIL I..VI, party dependencies, note refs by
# SAIL). JARUS SORA 2.5 Main Body, Table 14.
_OSO_TABLE: tuple[
    tuple[
        str,
        str,
        tuple[RobustnessLevel, ...],
        _PartyDependencies,
        dict[Sail, tuple[str, ...]],
    ],
    ...,
] = (
    (
        "OSO#01",
        "Ensure the operator is competent and/or proven",
        (_NR, _L, _M, _H, _H, _H),
        (_X, _DASH, _DASH),
        {},
    ),
    (
        "OSO#02",
        "UAS manufactured by competent and/or proven entity",
        (_NR, _NR, _L, _M, _H, _H),
        (_DASH, _DASH, _X),
        {},
    ),
    (
        "OSO#03",
        "UAS maintained by competent and/or proven entity",
        (_L, _L, _M, _M, _H, _H),
        ((1, 2), _DASH, (1,)),
        {},
    ),
    (
        "OSO#04",
        "UAS components essential to safe operations are designed to an Airworthiness Design Standard (ADS)",
        (_NR, _NR, _NR, _L, _M, _H),
        (_DASH, _DASH, _X),
        {},
    ),
    (
        "OSO#05",
        "UAS is designed considering system safety and reliability",
        (_NR, _NR, _L, _M, _H, _H),
        (_DASH, _DASH, _X),
        {Sail.II: ("4.9.3(c)",)},
    ),
    (
        "OSO#06",
        "C3 link characteristics are appropriate for the operation",
        (_NR, _L, _L, _M, _H, _H),
        (_X, _DASH, _X),
        {},
    ),
    (
        "OSO#07",
        "Conformity check of the UAS configuration",
        (_L, _L, _M, _M, _H, _H),
        ((1, 2), _DASH, (1,)),
        {},
    ),
    (
        "OSO#08",
        "Operational procedures are defined, validated and adhered to",
        (_L, _M, _H, _H, _H, _H),
        (_X, _DASH, (1,)),
        {},
    ),
    (
        "OSO#09",
        "Remote crew trained and current",
        (_L, _L, _M, _M, _H, _H),
        (_X, _X, _DASH),
        {},
    ),
    (
        "OSO#13",
        "External services supporting UAS operations are adequate to the operation",
        (_L, _L, _M, _H, _H, _H),
        (_X, _DASH, _DASH),
        {},
    ),
    (
        "OSO#16",
        "Multi crew coordination",
        (_L, _L, _M, _M, _H, _H),
        ((1, 3), (2,), _DASH),
        {},
    ),
    (
        "OSO#17",
        "Remote crew is fit to operate",
        (_L, _L, _M, _M, _H, _H),
        (_X, _DASH, _DASH),
        {},
    ),
    (
        "OSO#18",
        "Automatic protection of the flight envelope from human errors",
        (_NR, _NR, _L, _M, _H, _H),
        (_DASH, _DASH, _X),
        {},
    ),
    (
        "OSO#19",
        "Safe recovery from human error",
        (_NR, _NR, _L, _M, _M, _H),
        (_DASH, _DASH, _X),
        {},
    ),
    (
        "OSO#20",
        "A Human Factors evaluation has been performed and the HMI found appropriate for the mission",
        (_NR, _L, _L, _M, _M, _H),
        (_X, _DASH, _X),
        {},
    ),
    (
        "OSO#23",
        "Environmental conditions for safe operations defined, measurable and adhered to",
        (_L, _L, _M, _M, _H, _H),
        (_X, _DASH, _X),
        {},
    ),
    (
        "OSO#24",
        "UAS designed and qualified for adverse environmental conditions",
        (_NR, _NR, _M, _H, _H, _H),
        (_DASH, _DASH, _X),
        {},
    ),
)


def determine_sail(final_grc: int, arc: AirRiskClass) -> Sail | None:
    """Look up the SAIL from the final GRC and residual ARC."""
    if isinstance(final_grc, bool) or not isinstance(final_grc, int):
        raise TypeError("final_grc must be an integer, not bool or another type")
    if final_grc < 1:
        raise ValueError("final_grc must be at least 1")
    if final_grc > _MAX_SPECIFIC_CATEGORY_GRC:
        return None
    return _SAIL_MATRIX[final_grc][arc]


def _party_dependency(
    criterion_refs: _PartyCriterionRefs,
) -> OsoPartyDependency:
    return OsoPartyDependency(
        applicable=criterion_refs is not None,
        criterion_refs=list(criterion_refs or ()),
    )


def _party_dependencies(
    dependencies: _PartyDependencies,
) -> OsoPartyDependencies:
    operator, training_organisation, designer = dependencies
    return OsoPartyDependencies(
        operator=_party_dependency(operator),
        training_organisation=_party_dependency(training_organisation),
        designer=_party_dependency(designer),
    )


def applicable_osos(sail: Sail) -> list[OsoRequirement]:
    """Return every Table 14 OSO row, including explicit NR rows."""
    if not isinstance(sail, Sail):
        raise TypeError("sail must be a SAIL I-VI value")
    column = _SAIL_COLUMN_ORDER.index(sail)
    requirements: list[OsoRequirement] = []
    for oso_id, title, levels, dependencies, note_refs_by_sail in _OSO_TABLE:
        robustness = levels[column]
        requirements.append(
            OsoRequirement(
                oso_id=oso_id,
                title=title,
                robustness=robustness,
                required=robustness != RobustnessLevel.NOT_REQUIRED,
                note_refs=list(note_refs_by_sail.get(sail, ())),
                party_dependencies=_party_dependencies(dependencies),
            )
        )
    return requirements


__all__ = [
    "applicable_osos",
    "determine_sail",
]
