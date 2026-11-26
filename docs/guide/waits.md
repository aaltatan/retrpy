# Waits, backoff and jitter

Between two tries of the same segment, the plan waits

```text
wait = delay * backoff**k        # k = 0, 1, 2, ... restarting in each segment
wait = jitter(wait)              # if jitter is given
wait = min(wait, max_delay)      # if max_delay is given
```

and calls `sleep(wait)` only when `wait > 0`. With the defaults (`delay=0.0`) a plan never
sleeps.

## Exponential backoff

```python
from retrpy import attempt


def down() -> None:
    raise ConnectionError


waits = []

try:
    (attempt(down) * 4)(delay=0.5, backoff=2.0, sleep=waits.append)
except ExceptionGroup:
    pass

assert waits == [0.5, 1.0, 2.0]
```

There are three waits for four tries: no wait after the last one.

## Backoff restarts for each segment

In `primary * 3 + backup * 2`, the backup starts again from `delay` instead of inheriting
the primary's grown wait, and there is **no wait when switching** to the next source.

```python
from retrpy import attempt


def primary() -> float:
    raise ConnectionError("primary down")


backup_calls = []


def backup() -> float:
    backup_calls.append(1)

    if len(backup_calls) == 1:
        raise ConnectionError("backup busy")

    return 1.08


waits = []
plan = attempt(primary) * 3 + attempt(backup) * 2

assert plan(delay=0.1, backoff=2.0, sleep=waits.append) == 1.08
assert waits == [0.1, 0.2, 0.1]
```

To keep the backoff growing across sources, rotate them inside one segment instead, or
accept that each segment restarts. To wait before switching, put the wait in the fallback
attempt itself.

## Capping with `max_delay`

`max_delay` caps every single wait. It is applied last, after jitter.

```python
from retrpy import attempt


def down() -> None:
    raise ConnectionError


waits = []

try:
    (attempt(down) * 6)(delay=1.0, backoff=3.0, max_delay=10.0, sleep=waits.append)
except ExceptionGroup:
    pass

assert waits == [1.0, 3.0, 9.0, 10.0, 10.0]
```

!!! tip "Long retry budgets"
    If `delay * backoff**k` grows too big for a float (around 1,000 doublings), the wait
    becomes infinite instead of raising `OverflowError`, and `max_delay` caps it as usual.
    Without `max_delay`, an infinite wait makes `time.sleep` itself raise, so set a cap when
    the count is large.

## Jitter

Jitter spreads out clients that failed at the same moment so they don't retry in sync.
`jitter` receives the computed wait and returns the one to use. It owns its randomness, so
tests can pass a deterministic function.

```py
import random

full = lambda wait: random.uniform(0, wait)  # "full jitter"
equal = lambda wait: wait / 2 + random.uniform(0, wait / 2)  # "equal jitter"
twenty_percent = lambda wait: wait * random.uniform(0.8, 1.2)  # ±20%
```

```python
from retrpy import attempt


def down() -> None:
    raise ConnectionError


waits = []

try:
    (attempt(down) * 3)(delay=1.0, backoff=2.0, jitter=lambda wait: wait / 2, sleep=waits.append)
except ExceptionGroup:
    pass

assert waits == [0.5, 1.0]
```

A jitter that returns zero or less skips the sleep for that wait.
