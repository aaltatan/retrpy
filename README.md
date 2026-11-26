# retrpy

**Documentation: <https://aaltatan.github.io/retrpy/>**

Retry and fallback as **plans of attempts**, composed with ordinary Python operators.
Zero dependencies, fully typed.

```python
from retrpy import attempt

plan = (
    attempt(fetch_rate, client, primary_url) * 3  # try the primary 3 times
    + attempt(fetch_rate, client, backup_url) * 2  # then the backup twice
    + attempt(lambda: None)  # then give up with None
)
rate = plan(delay=0.05, backoff=2.0, catch=(NetworkError, RetryableHTTPError))
```

A plan is a value: build it once, run it as often as you like, pass it around, `len()` it.
The first attempt that succeeds wins.

## The problem it solves

A nightly job turns the day's orders into invoices, and each order total has to be converted
from USD to EUR. The exchange-rate provider is usually fine, but now and then it times out,
answers `503`, or rate-limits you with `429`. When that happens at 2 a.m., the job dies and
nobody gets invoiced.

You want: retry the main provider a few times with a growing wait, then switch to a second
provider, and as a last resort use yesterday's rate from your own database. Log every failure.
Never retry a real bug. And keep it testable without waiting for real.

Written by hand, that usually ends up like this:

```python
def get_rate() -> float:
    last_error = None
    wait = 0.5
    for url in (PRIMARY, SECONDARY):
        for _ in range(3):
            try:
                return fetch_rate(url, "USD", "EUR")
            except (TimeoutError, ConnectionError, RetryableHTTPError) as error:
                log.warning("rate fetch failed: %r", error)
                last_error = error
                time.sleep(wait)  # sleeps after the last try too
                wait *= 2  # the secondary inherits the primary's grown wait
    try:
        return load_cached_rate("USD", "EUR")
    except LookupError:
        raise last_error  # earlier failures are lost
```

It works, but it's hard to read and has quiet bugs. The secondary provider starts at a 4-second
wait instead of 0.5. It sleeps for nothing before switching source. Only the last error
survives. And `time.sleep` is hard-wired, so the tests really sleep.

With retrpy, the plan says exactly what you meant, and the bugs go away:

```python
import logging

from retrpy import attempt

log = logging.getLogger("invoicing")

rate_plan = (
    attempt(fetch_rate, PRIMARY, "USD", "EUR") * 3  # main provider, 3 tries
    + attempt(fetch_rate, SECONDARY, "USD", "EUR") * 3  # backup provider, fresh backoff
    + attempt(load_cached_rate, "USD", "EUR")  # yesterday's rate from the database
)


def get_rate(sleep=time.sleep) -> float:
    return rate_plan(
        delay=0.5,
        backoff=2.0,
        max_delay=10.0,
        catch=(TimeoutError, ConnectionError, RetryableHTTPError, LookupError),
        on_failure=lambda error, n: log.warning("rate attempt %d failed: %r", n, error),
        sleep=sleep,
    )
```

What you get:

- **Each provider gets its own backoff**: 0.5 s and 1 s between the primary's tries, then the
  same again for the secondary. There's no wait when switching source.
- **Bugs fail fast.** A `KeyError` from a changed JSON shape isn't in `catch`, so it surfaces on
  the first try, unwrapped, with its real traceback.
- **Nothing is lost.** If even the cache is empty, the job raises one `ExceptionGroup` with all
  seven failures, so the morning report shows exactly what went wrong and in what order.
- **Tests are instant.** Pass `sleep=waits.append` and assert on the waits.
- **The policy is a value.** `rate_plan` can be imported, reused by another job, or extended
  with `+`.

## Install

```bash
uv add retrpy
```

```bash
pip install retrpy
```

## Building plans

| Expression | Meaning |
| --- | --- |
| `attempt(fn, *args, **kwargs)` | one attempt of `fn(*args, **kwargs)` |
| `p * n` or `n * p` | retry: repeat `n` times (`n >= 1`) |
| `p + q` | fallback: run `q`'s attempts after `p`'s |
| `+ attempt(lambda: default)` | a default value is just one more attempt |

The operators behave like they do on tuples: `(a * 2) * 3` is six attempts of `a`, and
`(a * 2 + b) * 3` repeats the whole sequence three times.

## Running

```python
plan(
    delay=0.0,  # first wait between retries, in seconds
    backoff=1.0,  # each next wait is multiplied by this
    catch=(Exception,),  # only these are retried; anything else propagates at once
    max_delay=None,  # cap on a single wait
    jitter=None,  # e.g. lambda d: d * random.uniform(0.5, 1.0)
    on_failure=None,  # e.g. lambda error, number: log.warning("attempt %d: %r", number, error)
    sleep=time.sleep,  # inject a fake in tests
)
```

- Backoff **restarts for each segment**. In `primary * 3 + backup * 2`, the backup starts again
  from `delay` instead of inheriting the primary's grown wait. There's no wait when switching
  to the next source.
- The wait is `delay * backoff**k`, then `jitter`, then capped by `max_delay`. A wait of zero
  or less doesn't sleep.
- Long retry budgets are safe with a cap. If `delay * backoff**k` grows too big for a float
  (around 1,000 doublings), the wait becomes infinite instead of raising `OverflowError`, and
  `max_delay` caps it as usual. Without `max_delay`, set a cap or keep the count reasonable:
  an infinite wait makes `time.sleep` itself raise.
- Errors outside `catch` propagate immediately and unwrapped. `KeyboardInterrupt` and other
  `BaseException`s are never caught.
- To retry on a bad *result*, make the attempt raise: for example, turn HTTP 429/5xx into a
  `RetryableHTTPError`.

## When everything fails

All failures are raised together, in order, as an `ExceptionGroup`:

```python
try:
    rate = plan(catch=(NetworkError,))
except* NetworkError as group:
    for error in group.exceptions:
        log.error("failed: %r", error)
```

## Examples

### HTTP with a mirror and a default

Retry on a bad *response* by making the attempt raise. Here, 429 and 5xx become
`RetryableHTTPError`; a 404 stays an `HTTPError` and fails fast, because it's not in `catch`.

```python
import json
import urllib.error
import urllib.request

from retrpy import attempt


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


plan = (
    attempt(fetch_rate, "https://api.example.com", "EUR") * 3
    + attempt(fetch_rate, "https://mirror.example.com", "EUR") * 2
    + attempt(lambda: None)
)  # Plan[float | None]

rate = plan(
    delay=0.2,
    backoff=2.0,
    catch=(urllib.error.URLError, TimeoutError, RetryableHTTPError),
)
```

The waits are `0.2, 0.4` on the primary, then no wait, then `0.2` on the mirror: the
mirror's backoff starts fresh.

### Exponential backoff with full jitter and a cap

Jitter spreads out clients that failed at the same moment, so they don't all retry in sync.
`jitter` gets the computed wait and returns the one to use; `max_delay` caps the result.

```python
import random

result = (attempt(call_service) * 8)(
    delay=0.1,
    backoff=2.0,
    jitter=lambda wait: random.uniform(0, wait),  # "full jitter"
    max_delay=5.0,
    catch=(ConnectionError, TimeoutError),
)
```

Other common shapes are `lambda w: w / 2 + random.uniform(0, w / 2)` ("equal jitter") and
`lambda w: w * random.uniform(0.8, 1.2)` (±20%).

### Logging every failure

`on_failure` sees each caught error and its number across the whole plan, including the last.

```python
import logging

log = logging.getLogger(__name__)

plan = attempt(fetch_rate, primary, "EUR") * 3 + attempt(fetch_rate, mirror, "EUR") * 2

rate = plan(
    delay=0.2,
    catch=(OSError, RetryableHTTPError),
    on_failure=lambda error, n: log.warning("attempt %d/%d failed: %r", n, len(plan), error),
)
```

### Building plans from data

Plans are values, so ordinary Python builds them. Fall back through a list of mirrors:

```python
from functools import reduce
from operator import add

MIRRORS = ["https://a.example.com", "https://b.example.com", "https://c.example.com"]

plan = reduce(add, (attempt(fetch_rate, url, "EUR") * 2 for url in MIRRORS))

len(plan)  # 6
```

Or rotate through sources instead of exhausting each one first. Multiplying a multi-segment
plan repeats the whole sequence, like a tuple:

```python
rotation = (attempt(fetch_rate, MIRRORS[0], "EUR") + attempt(fetch_rate, MIRRORS[1], "EUR")) * 3
# a, b, a, b, a, b
```

### Reusable fragments

Name the parts once and combine them where they're used:

```python
from_api = attempt(load_user_from_api, user_id) * 3
from_cache = attempt(load_user_from_cache, user_id)
anonymous = attempt(lambda: ANONYMOUS_USER)

strict = from_api  # must come from the API, or raise
relaxed = from_api + from_cache + anonymous  # always returns a user

user = relaxed(delay=0.1, catch=(OSError, CacheMiss))
```

### Waiting for a service to come up

Any callable works, including standard library functions with arguments:

```python
import socket

connection = (attempt(socket.create_connection, ("db.internal", 5432), timeout=2) * 10)(
    delay=0.5,
    backoff=1.5,
    max_delay=5.0,
    catch=(OSError,),
)
```

### Failing fast on bugs

Only the errors in `catch` are retried. Everything else, like a bug in your parsing code,
propagates on the first try, unwrapped, with its original traceback:

```python
def fetch_and_parse() -> Order:
    payload = fetch_order()  # may raise ConnectionError: retried
    return Order.from_json(payload)  # may raise KeyError: a bug, raised at once


order = (attempt(fetch_and_parse) * 5)(catch=(ConnectionError,))
```

`catch=()` retries nothing, and every error propagates at once. `catch` never accepts
`BaseException`, so Ctrl-C always stops the run.

### Handling the failures by type

When every attempt fails, `except*` lets you handle each kind of error separately:

```python
try:
    rate = plan(catch=(urllib.error.URLError, RetryableHTTPError))
except* RetryableHTTPError as group:
    codes = [error.args[0] for error in group.exceptions]
    log.error("server kept failing: %s", codes)
    rate = None
except* urllib.error.URLError:
    log.error("network unreachable")
    rate = None
```

Or catch the whole group and inspect it:

```python
try:
    rate = plan(catch=(OSError,))
except ExceptionGroup as group:
    last = group.exceptions[-1]
    timeouts = group.subgroup(TimeoutError)
```

## Testing

Pass a fake `sleep` so tests run instantly and you can assert on the waits:

```python
waits = []
plan(delay=0.05, backoff=2.0, sleep=waits.append)
assert waits == [0.05, 0.1]
```

A scripted fake makes each attempt's outcome explicit:

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
```

## With pyflowstep

A pyflowstep `Flow` is a callable, so it can be an attempt as is:

```python
plan = attempt(login_flow, page, user=user) * 3 + attempt(sso_login_flow, page)
page = plan(delay=0.5, catch=(TimeoutError,))
```
