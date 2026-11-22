import dataclasses

import pytest

import retrpy
from retrpy import Plan, attempt
from retrpy._plan import Segment


class TestAttempt:
    def test_binds_arguments(self) -> None:
        plan = attempt(pow, 2, exp=3)

        assert len(plan.segments) == 1
        assert plan.segments[0].count == 1
        assert plan.segments[0].fn() == 8

    def test_len_and_iter_expand_counts(self) -> None:
        plan = Plan((Segment(lambda: 1, 2), Segment(lambda: 2, 1)))

        assert len(plan) == 3
        assert [f() for f in plan] == [1, 1, 2]

    def test_is_immutable(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            attempt(int).segments = ()  # type: ignore[misc]

    def test_public_api(self) -> None:
        assert retrpy.__all__ == ["Plan", "attempt"]
