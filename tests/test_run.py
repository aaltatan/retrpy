import pytest

from retrpy import Plan, attempt
from tests.fakes import FakeSleep, NetworkError, Scripted


class TestSuccess:
    def test_success_first_try(self, sleep: FakeSleep) -> None:
        assert attempt(lambda: 5)(sleep=sleep) == 5
        assert sleep.calls == []

    def test_retry_then_success(self, sleep: FakeSleep) -> None:
        fn = Scripted(NetworkError(), NetworkError(), 7)

        assert (attempt(fn) * 3)(delay=0.05, backoff=2.0, sleep=sleep) == 7
        assert sleep.calls == [0.05, 0.1]

    def test_zero_delay_never_sleeps(self, sleep: FakeSleep) -> None:
        fn = Scripted(NetworkError(), 1)

        assert (attempt(fn) * 2)(sleep=sleep) == 1
        assert sleep.calls == []


class TestFallback:
    def test_fallback_backoff_restarts_per_segment(self, sleep: FakeSleep) -> None:
        primary = Scripted(NetworkError())
        backup = Scripted(NetworkError(), 9)
        plan = attempt(primary) * 3 + attempt(backup) * 2

        assert plan(delay=0.05, backoff=2.0, sleep=sleep) == 9
        assert sleep.calls == [0.05, 0.1, 0.05]

    def test_default_value_step(self, sleep: FakeSleep) -> None:
        plan = attempt(Scripted(NetworkError())) * 2 + attempt(lambda: None)

        assert plan(sleep=sleep) is None

    def test_runs_are_independent(self, sleep: FakeSleep) -> None:
        plan = attempt(Scripted(NetworkError())) * 3 + attempt(lambda: 0)

        plan(delay=1, backoff=2, sleep=sleep)
        plan(delay=1, backoff=2, sleep=sleep)

        assert sleep.calls == [1, 2, 1, 2]


class TestFailFast:
    def test_fail_fast_outside_catch(self, sleep: FakeSleep) -> None:
        err = ValueError("bad")
        fn = Scripted(err, 1)

        with pytest.raises(ValueError, match="bad") as excinfo:
            (attempt(fn) * 3)(catch=(KeyError,), sleep=sleep)

        assert excinfo.value is err
        assert fn.calls == 1

    def test_keyboard_interrupt_propagates(self, sleep: FakeSleep) -> None:
        fn = Scripted(KeyboardInterrupt(), 1)

        with pytest.raises(KeyboardInterrupt):
            (attempt(fn) * 3)(sleep=sleep)

        assert fn.calls == 1


class TestExhausted:
    def test_exhausted_raises_exception_group(self, sleep: FakeSleep) -> None:
        errors = [NetworkError(1), NetworkError(2), NetworkError(3)]
        plan = attempt(Scripted(*errors)) * 3

        with pytest.raises(ExceptionGroup, match="all 3 attempts failed") as excinfo:
            plan(sleep=sleep)

        assert list(excinfo.value.exceptions) == errors

    def test_empty_plan_raises(self, sleep: FakeSleep) -> None:
        with pytest.raises(ValueError, match="empty"):
            Plan(())(sleep=sleep)
