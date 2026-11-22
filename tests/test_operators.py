from typing import Any

import pytest

from retrpy import Plan, attempt


def shape(plan: Plan[Any]) -> list[tuple[object, int]]:
    return [(segment.fn, segment.count) for segment in plan.segments]


@pytest.fixture
def a() -> Plan[int]:
    return attempt(int)


@pytest.fixture
def b() -> Plan[str]:
    return attempt(str)


class TestMul:
    def test_mul_single_segment_multiplies_count(self, a: Plan[int]) -> None:
        fa = a.segments[0].fn

        assert shape((a * 2) * 3) == [(fa, 6)]

    def test_rmul_matches_mul(self, a: Plan[int]) -> None:
        assert 3 * a == a * 3

    def test_mul_multi_segment_repeats_sequence(self, a: Plan[int], b: Plan[str]) -> None:
        fa, fb = a.segments[0].fn, b.segments[0].fn

        assert shape((a * 2 + b) * 3) == [(fa, 2), (fb, 1)] * 3

    @pytest.mark.parametrize("n", [0, -1])
    def test_mul_rejects_zero_and_negative(self, a: Plan[int], n: int) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            a * n


class TestAdd:
    def test_add_never_merges(self, a: Plan[int]) -> None:
        fa = a.segments[0].fn

        assert shape(a * 2 + a * 3) == [(fa, 2), (fa, 3)]


class TestOperands:
    def test_wrong_operand_types_raise_type_error(self, a: Plan[int]) -> None:
        with pytest.raises(TypeError):
            a + 3  # type: ignore[operator]

        with pytest.raises(TypeError):
            a * 2.0  # type: ignore[operator]

    def test_subclass_preserved(self, a: Plan[int], b: Plan[str]) -> None:
        class P[T](Plan[T]):
            pass

        p = P(a.segments)

        assert type(p * 2) is P
        assert type(p + b) is P
