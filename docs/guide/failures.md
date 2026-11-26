# When everything fails

## Every failure, in one `ExceptionGroup`

When every attempt fails, the plan raises an `ExceptionGroup` whose message is
`all N attempts failed` and whose `exceptions` are every caught failure, in the order they
happened. Nothing is lost.

```python
from retrpy import attempt


def down(name: str) -> None:
    raise ConnectionError(name)


plan = attempt(down, "primary") * 2 + attempt(down, "backup")

try:
    plan(catch=(ConnectionError,))
except ExceptionGroup as group:
    assert str(group) == "all 3 attempts failed (3 sub-exceptions)"
    assert [error.args[0] for error in group.exceptions] == ["primary", "primary", "backup"]
```

## Handling each kind with `except*`

Different sources may fail differently. `except*` handles each kind separately:

```python
from retrpy import attempt


def network() -> float:
    raise ConnectionError("unreachable")


def cache() -> float:
    raise LookupError("no cached rate")


handled = []

try:
    rate = (attempt(network) * 2 + attempt(cache))(catch=(ConnectionError, LookupError))
except* ConnectionError as group:
    handled.append(("network", len(group.exceptions)))
    rate = None
except* LookupError as group:
    handled.append(("cache", len(group.exceptions)))
    rate = None

assert handled == [("network", 2), ("cache", 1)]
assert rate is None
```

Or catch the whole group and inspect it with the standard methods, such as
`group.subgroup(TimeoutError)` or `group.exceptions[-1]`.

## Logging each failure with `on_failure`

`on_failure(error, number)` is called for **every caught failure**, numbered from 1 across
the whole plan, including the last one before the plan gives up.

```python
import logging

from retrpy import attempt

log = logging.getLogger("rates")
seen = []


def down() -> float:
    raise TimeoutError("slow")


def from_cache() -> float:
    return 1.08


plan = attempt(down) * 3 + attempt(from_cache)


def report(error: Exception, number: int) -> None:
    log.warning("attempt %d/%d failed: %r", number, len(plan), error)
    seen.append(number)


assert plan(catch=(TimeoutError,), on_failure=report) == 1.08
assert seen == [1, 2, 3]
```

`on_failure` is not called for errors outside `catch`: those propagate at once. If the hook
itself raises, that error propagates and the run stops.
