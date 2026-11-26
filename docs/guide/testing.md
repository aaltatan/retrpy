# Testing

Side effects are parameters. Pass a fake `sleep` so tests run instantly and you can assert
on the waits:

```py
waits = []
plan(delay=0.05, backoff=2.0, sleep=waits.append)
assert waits == [0.05, 0.1]
```

`sleep` can be any callable that takes the number of seconds; its return value is ignored.

## A scripted fake

A small fake that returns or raises each outcome in turn makes every attempt explicit:

```python
import pytest

from retrpy import attempt


class Scripted:
    """Returns or raises each outcome in turn; the last one repeats."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = outcomes, 0

    def __call__(self):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1

        if isinstance(outcome, BaseException):
            raise outcome

        return outcome


def test_falls_back_to_mirror():
    primary = Scripted(ConnectionError("down"))
    mirror = Scripted(ConnectionError("busy"), 1.08)
    waits = []

    plan = attempt(primary) * 3 + attempt(mirror) * 2
    rate = plan(delay=0.1, backoff=2.0, catch=(ConnectionError,), sleep=waits.append)

    assert rate == 1.08
    assert (primary.calls, mirror.calls) == (3, 2)
    assert waits == [0.1, 0.2, 0.1]


def test_gives_up_with_every_error():
    plan = attempt(Scripted(ConnectionError("down"))) * 2

    with pytest.raises(ExceptionGroup, match="all 2 attempts failed") as excinfo:
        plan(catch=(ConnectionError,), sleep=lambda _: None)

    assert len(excinfo.value.exceptions) == 2


test_falls_back_to_mirror()
test_gives_up_with_every_error()
```

## Injecting `sleep` into your own code

Keep the plan at module level and let the function that runs it take `sleep`, defaulting to
`time.sleep`. Production calls it with no argument; tests pass `waits.append`.

```py
import time

rate_plan = attempt(fetch_rate, PRIMARY, "USD", "EUR") * 3 + attempt(load_cached_rate, "USD", "EUR")


def get_rate(sleep=time.sleep) -> float:
    return rate_plan(delay=0.5, backoff=2.0, catch=(TimeoutError, LookupError), sleep=sleep)
```

A deterministic `jitter` (for example `lambda wait: wait / 2`) keeps jittered waits
assertable too.
