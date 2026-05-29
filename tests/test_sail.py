import pytest

from estimator.execution.sail import applicable_osos, determine_sail
from schemas.sora import AirRiskClass, RobustnessLevel, Sail

# Independent transcription of the SORA SAIL determination table, rows = final
# GRC, columns = residual ARC (a, b, c, d). Every cell is asserted below.
_EXPECTED_SAIL = {
    1: (Sail.I, Sail.II, Sail.IV, Sail.VI),
    2: (Sail.I, Sail.II, Sail.IV, Sail.VI),
    3: (Sail.II, Sail.II, Sail.IV, Sail.VI),
    4: (Sail.III, Sail.III, Sail.IV, Sail.VI),
    5: (Sail.IV, Sail.IV, Sail.IV, Sail.VI),
    6: (Sail.V, Sail.V, Sail.V, Sail.VI),
    7: (Sail.VI, Sail.VI, Sail.VI, Sail.VI),
}

_ARC_COLUMNS = (AirRiskClass.A, AirRiskClass.B, AirRiskClass.C, AirRiskClass.D)


@pytest.mark.parametrize("grc", sorted(_EXPECTED_SAIL))
@pytest.mark.parametrize("column", range(4))
def test_determine_sail_every_cell(grc: int, column: int) -> None:
    arc = _ARC_COLUMNS[column]
    assert determine_sail(grc, arc) == _EXPECTED_SAIL[grc][column]


@pytest.mark.parametrize("grc", [8, 9, 20])
@pytest.mark.parametrize("arc", _ARC_COLUMNS)
def test_grc_above_seven_is_certified_category(grc: int, arc: AirRiskClass) -> None:
    assert determine_sail(grc, arc) == Sail.CERTIFIED


def test_grc_below_one_clamps_to_one() -> None:
    assert determine_sail(0, AirRiskClass.A) == Sail.I


def test_applicable_osos_excludes_optional() -> None:
    osos = applicable_osos(Sail.II)
    assert osos
    assert all(o.robustness != RobustnessLevel.OPTIONAL for o in osos)
    # OSO#04 is optional through SAIL III, so it is absent at SAIL II.
    assert "OSO#04" not in {o.oso_id for o in osos}


def test_applicable_osos_grows_with_sail() -> None:
    counts = [len(applicable_osos(s)) for s in (Sail.I, Sail.III, Sail.VI)]
    assert counts == sorted(counts)
    assert len(applicable_osos(Sail.VI)) == 24


def test_certified_has_no_osos() -> None:
    assert applicable_osos(Sail.CERTIFIED) == []
