import pytest

from retrpy import attempt
from tests.fakes import FakeSleep, NetworkError, Scripted


class TestWait:
    def test_jitter_applied(self, sleep: FakeSleep) -> None:
        plan = attempt(Scripted(NetworkError(), 1)) * 2

        plan(delay=0.1, jitter=lambda d: d / 2, sleep=sleep)

        assert sleep.calls == [0.05]

    def test_max_delay_caps_after_jitter(self, sleep: FakeSleep) -> None:
        plan = attempt(Scripted(NetworkError(), NetworkError(), 1)) * 3

        plan(delay=1, backoff=10, jitter=lambda d: d + 1, max_delay=5, sleep=sleep)

        assert sleep.calls == [2, 5]

    def test_nonpositive_jitter_skips_sleep(self, sleep: FakeSleep) -> None:
        plan = attempt(Scripted(NetworkError(), 1)) * 2

        plan(delay=1, jitter=lambda d: -1, sleep=sleep)

        assert sleep.calls == []


class TestOnFailure:
    def test_on_failure_every_caught_failure_including_last(self, sleep: FakeSleep) -> None:
        errors = [NetworkError(1), NetworkError(2), NetworkError(3)]
        seen: list[tuple[Exception, int]] = []

        with pytest.raises(ExceptionGroup):
            (attempt(Scripted(*errors)) * 3)(
                on_failure=lambda e, n: seen.append((e, n)), sleep=sleep
            )

        assert seen == [(errors[0], 1), (errors[1], 2), (errors[2], 3)]

    def test_on_failure_numbers_across_segments(self, sleep: FakeSleep) -> None:
        numbers: list[int] = []
        plan = attempt(Scripted(NetworkError())) * 2 + attempt(lambda: 1)

        assert plan(on_failure=lambda e, n: numbers.append(n), sleep=sleep) == 1

        assert numbers == [1, 2]

    def test_on_failure_numbers_continue_into_fallback(self, sleep: FakeSleep) -> None:
        numbers: list[int] = []
        plan = attempt(Scripted(NetworkError())) * 2 + attempt(Scripted(NetworkError()))

        with pytest.raises(ExceptionGroup):
            plan(on_failure=lambda e, n: numbers.append(n), sleep=sleep)

        assert numbers == [1, 2, 3]

    def test_on_failure_not_called_for_fail_fast(self, sleep: FakeSleep) -> None:
        seen: list[int] = []

        with pytest.raises(ValueError, match="bad"):
            (attempt(Scripted(ValueError("bad"))) * 2)(
                catch=(NetworkError,), on_failure=lambda e, n: seen.append(n), sleep=sleep
            )

        assert seen == []

    def test_on_failure_error_propagates(self, sleep: FakeSleep) -> None:
        fn = Scripted(NetworkError(), 1)

        def hook(error: Exception, number: int) -> None:
            raise RuntimeError("hook broke")

        with pytest.raises(RuntimeError, match="hook broke"):
            (attempt(fn) * 2)(on_failure=hook, sleep=sleep)

        assert fn.calls == 1
