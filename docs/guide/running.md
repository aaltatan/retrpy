# Running a plan

Call the plan with keyword arguments. All of them are optional:

```py
plan(
    delay=0.0,  # first wait between retries, in seconds
    backoff=1.0,  # each next wait is multiplied by this
    catch=(Exception,),  # only these are retried; anything else propagates at once
    max_delay=None,  # cap on a single wait
    jitter=None,  # e.g. lambda wait: wait * random.uniform(0.5, 1.0)
    on_failure=None,  # e.g. lambda error, number: log.warning("attempt %d: %r", number, error)
    sleep=time.sleep,  # inject a fake in tests
)
```

The attempts run in order and **the first one that succeeds wins**: its return value is
returned and the rest never run. Each call is independent, so a plan can be run as often as
you like.

## `catch`: what is worth retrying

Only exceptions in `catch` count as failures to retry. The default, `(Exception,)`, retries
everything; in real code, name the transient errors.

```python
from retrpy import attempt

calls = []


def flaky() -> int:
    calls.append(1)

    if len(calls) == 1:
        raise TimeoutError

    return 42


assert (attempt(flaky) * 3)(catch=(TimeoutError, ConnectionError)) == 42
```

## Bugs fail fast

An exception outside `catch` propagates **at once and unwrapped**, with its original
traceback. No more attempts run.

```python
import pytest

from retrpy import attempt

calls = []


def parse() -> dict[str, int]:
    calls.append(1)

    return {}["missing"]  # a bug, not a network problem


with pytest.raises(KeyError):
    (attempt(parse) * 5)(catch=(ConnectionError,))

assert len(calls) == 1
```

`catch=()` retries nothing: every error propagates on the first try.

## Ctrl-C always stops the run

`catch` only accepts `Exception` subclasses. `KeyboardInterrupt`, `SystemExit` and
`asyncio.CancelledError` are `BaseException`s and are never caught. Passing one in `catch`
raises `TypeError` before any attempt runs.

```python
import pytest

from retrpy import attempt

with pytest.raises(TypeError, match="never BaseException"):
    attempt(int, "1")(catch=(BaseException,))
```

## Retrying on a bad result

Exceptions are the only failure signal. To retry on a result, make the attempt check it and
raise. For example, turn HTTP 429 and 5xx into an error you put in `catch`, and let a 404
fail fast:

```python
import json
import urllib.error
import urllib.request


class RetryableHTTPError(Exception):
    pass


def fetch_rate(url: str, currency: str) -> float:
    try:
        with urllib.request.urlopen(f"{url}/rates/{currency}", timeout=5) as response:
            return float(json.load(response)["rate"])

    except urllib.error.HTTPError as error:
        if error.code == 429 or error.code >= 500:
            raise RetryableHTTPError(error.code) from error

        raise
```

## An empty plan

`Plan(())` has no attempts; calling it raises `ValueError`. You only get one by building a
`Plan` by hand: `attempt`, `*` and `+` never produce an empty plan.
