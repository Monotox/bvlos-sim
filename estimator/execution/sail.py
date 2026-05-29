"""SORA SAIL determination and Operational Safety Objective (OSO) assignment.

The SAIL is looked up from the final Ground Risk Class and the residual Air Risk
Class. The applicable OSOs and their required robustness are a static function of
the SAIL.

The matrices below transcribe the JARUS SORA 2.0 SAIL determination table
(main body) and the OSO robustness assignment table (Annex E). They are kept as
single auditable constants; verify any cell against the official annex before
relying on it. Robustness levels: O (optional), L (low), M (medium), H (high).
"""

from schemas.sora import AirRiskClass, OsoRequirement, RobustnessLevel, Sail

_O = RobustnessLevel.OPTIONAL
_L = RobustnessLevel.LOW
_M = RobustnessLevel.MEDIUM
_H = RobustnessLevel.HIGH

_MAX_SPECIFIC_CATEGORY_GRC = 7

# Final GRC (1..7) x residual ARC -> SAIL. SORA 2.0 main body SAIL table.
_SAIL_MATRIX: dict[int, dict[AirRiskClass, Sail]] = {
    1: {AirRiskClass.A: Sail.I, AirRiskClass.B: Sail.II, AirRiskClass.C: Sail.IV, AirRiskClass.D: Sail.VI},
    2: {AirRiskClass.A: Sail.I, AirRiskClass.B: Sail.II, AirRiskClass.C: Sail.IV, AirRiskClass.D: Sail.VI},
    3: {AirRiskClass.A: Sail.II, AirRiskClass.B: Sail.II, AirRiskClass.C: Sail.IV, AirRiskClass.D: Sail.VI},
    4: {AirRiskClass.A: Sail.III, AirRiskClass.B: Sail.III, AirRiskClass.C: Sail.IV, AirRiskClass.D: Sail.VI},
    5: {AirRiskClass.A: Sail.IV, AirRiskClass.B: Sail.IV, AirRiskClass.C: Sail.IV, AirRiskClass.D: Sail.VI},
    6: {AirRiskClass.A: Sail.V, AirRiskClass.B: Sail.V, AirRiskClass.C: Sail.V, AirRiskClass.D: Sail.VI},
    7: {AirRiskClass.A: Sail.VI, AirRiskClass.B: Sail.VI, AirRiskClass.C: Sail.VI, AirRiskClass.D: Sail.VI},
}

# SAIL ordering used to index the per-OSO robustness tuples below.
_SAIL_COLUMN_ORDER = (Sail.I, Sail.II, Sail.III, Sail.IV, Sail.V, Sail.VI)

# (OSO id, title, robustness per SAIL I..VI). SORA 2.0 Annex E.
_OSO_TABLE: tuple[tuple[str, str, tuple[RobustnessLevel, ...]], ...] = (
    ("OSO#01", "Ensure the operator is competent and/or proven", (_O, _L, _M, _H, _H, _H)),
    ("OSO#02", "UAS manufactured by competent and/or proven entity", (_O, _O, _L, _M, _H, _H)),
    ("OSO#03", "UAS maintained by competent and/or proven entity", (_L, _L, _M, _M, _H, _H)),
    ("OSO#04", "UAS developed to authority-recognized design standards", (_O, _O, _O, _L, _M, _H)),
    ("OSO#05", "UAS is designed considering system safety and reliability", (_O, _O, _L, _M, _H, _H)),
    ("OSO#06", "C3 link characteristics appropriate for the operation", (_O, _O, _L, _L, _M, _H)),
    ("OSO#07", "Inspection of the UAS to ensure consistency with the ConOps", (_L, _L, _M, _M, _H, _H)),
    ("OSO#08", "Operational procedures are defined, validated and adhered to", (_L, _M, _H, _H, _H, _H)),
    ("OSO#09", "Remote crew trained and current to control the abnormal situation", (_L, _L, _M, _M, _H, _H)),
    ("OSO#10", "Safe recovery from technical issue", (_L, _L, _M, _M, _H, _H)),
    ("OSO#11", "Procedures to handle deterioration of external systems", (_L, _M, _H, _H, _H, _H)),
    ("OSO#12", "UAS designed to manage deterioration of external systems", (_L, _L, _M, _M, _H, _H)),
    ("OSO#13", "External services supporting UAS operations are adequate", (_L, _L, _M, _H, _H, _H)),
    ("OSO#14", "Operational procedures defined, validated and adhered to (human error)", (_L, _M, _H, _H, _H, _H)),
    ("OSO#15", "Remote crew trained and current (human error)", (_L, _L, _M, _M, _H, _H)),
    ("OSO#16", "Multi-crew coordination", (_L, _L, _M, _M, _H, _H)),
    ("OSO#17", "Remote crew is fit to operate", (_L, _L, _M, _M, _H, _H)),
    ("OSO#18", "Automatic protection of the flight envelope from human error", (_O, _O, _L, _M, _H, _H)),
    ("OSO#19", "Safe recovery from human error", (_O, _O, _L, _M, _M, _H)),
    ("OSO#20", "A human factors evaluation has been performed", (_O, _L, _L, _M, _M, _H)),
    ("OSO#21", "Operational procedures defined for adverse conditions", (_L, _M, _H, _H, _H, _H)),
    ("OSO#22", "Remote crew trained to identify and avoid adverse conditions", (_L, _L, _M, _M, _M, _H)),
    ("OSO#23", "Environmental conditions for safe operations defined and adhered to", (_L, _L, _M, _M, _H, _H)),
    ("OSO#24", "UAS designed and qualified for adverse environmental conditions", (_O, _O, _M, _H, _H, _H)),
)


def determine_sail(final_grc: int, arc: AirRiskClass) -> Sail:
    """Look up the SAIL from the final GRC and residual ARC."""
    if final_grc > _MAX_SPECIFIC_CATEGORY_GRC:
        return Sail.CERTIFIED
    clamped_grc = max(final_grc, 1)
    return _SAIL_MATRIX[clamped_grc][arc]


def applicable_osos(sail: Sail) -> list[OsoRequirement]:
    """Return the OSOs that apply at a SAIL, excluding optional ones."""
    if sail == Sail.CERTIFIED:
        return []
    column = _SAIL_COLUMN_ORDER.index(sail)
    return [
        OsoRequirement(oso_id=oso_id, title=title, robustness=levels[column])
        for oso_id, title, levels in _OSO_TABLE
        if levels[column] != RobustnessLevel.OPTIONAL
    ]


__all__ = [
    "applicable_osos",
    "determine_sail",
]
