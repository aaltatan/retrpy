# Recipes

Complete programs for common jobs. Each one is self-contained.

## Exchange rate with a backup provider and a cached fallback

A nightly invoicing job needs the USD to EUR rate. Retry the main provider with a growing
wait, then the backup with a fresh backoff, then use yesterday's rate. Log every failure,
never retry a real bug, and keep it testable.

```python
import logging
import time

from retrpy import attempt

log = logging.getLogger("invoicing")

PRIMARY = "https://rates.example.com"
SECONDARY = "https://backup-rates.example.com"


class RetryableHTTPError(Exception):
    pass


def fetch_rate(url: str, source: str, target: str) -> float:
    raise TimeoutError(f"{url} timed out")  # stands in for a real HTTP call


def load_cached_rate(source: str, target: str) -> float:
    return 0.92  # stands in for a database query


rate_plan = (
    attempt(fetch_rate, PRIMARY, "USD", "EUR") * 3
    + attempt(fetch_rate, SECONDARY, "USD", "EUR") * 3
    + attempt(load_cached_rate, "USD", "EUR")
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


waits = []

assert get_rate(sleep=waits.append) == 0.92
assert waits == [0.5, 1.0, 0.5, 1.0]
```

If even the cache is empty (`LookupError`), the job raises one `ExceptionGroup` with all
seven failures, in order.

## Exponential backoff with full jitter and a cap

```py
import random

result = (attempt(call_service) * 8)(
    delay=0.1,
    backoff=2.0,
    jitter=lambda wait: random.uniform(0, wait),  # "full jitter"
    max_delay=5.0,
    catch=(ConnectionError, TimeoutError),
)
```

## Waiting for a service to come up

Any callable works, including standard library functions with arguments:

```py
import socket

connection = (attempt(socket.create_connection, ("db.internal", 5432), timeout=2) * 10)(
    delay=0.5,
    backoff=1.5,
    max_delay=5.0,
    catch=(OSError,),
)
```

## Falling back through a list of mirrors

```python
from functools import reduce
from operator import add

from retrpy import attempt

MIRRORS = ["https://a.example.com", "https://b.example.com", "https://c.example.com"]
tried = []


def download(url: str) -> bytes:
    tried.append(url)

    if url != MIRRORS[-1]:
        raise ConnectionError(url)

    return b"payload"


plan = reduce(add, (attempt(download, url) * 2 for url in MIRRORS))

assert plan(catch=(ConnectionError,)) == b"payload"
assert tried == [MIRRORS[0], MIRRORS[0], MIRRORS[1], MIRRORS[1], MIRRORS[2]]
```

To rotate through sources instead of exhausting each one first, multiply a multi-segment plan:
`(attempt(download, a) + attempt(download, b)) * 3` tries `a, b, a, b, a, b`.

## Reusable fragments

Name the parts once and combine them where they're used:

```python
from retrpy import attempt

ANONYMOUS_USER = {"name": "anonymous"}


class CacheMiss(Exception):
    pass


def load_user_from_api(user_id: int) -> dict[str, str]:
    raise OSError("api down")


def load_user_from_cache(user_id: int) -> dict[str, str]:
    raise CacheMiss(user_id)


user_id = 7
from_api = attempt(load_user_from_api, user_id) * 3
from_cache = attempt(load_user_from_cache, user_id)
anonymous = attempt(lambda: ANONYMOUS_USER)

strict = from_api  # must come from the API, or raise
relaxed = from_api + from_cache + anonymous  # always returns a user

assert relaxed(catch=(OSError, CacheMiss)) == ANONYMOUS_USER
```

## With pyflowstep

A [pyflowstep](https://pypi.org/project/pyflowstep/) `Flow` is a callable, so it can be an
attempt as is:

```py
plan = attempt(login_flow, page, user=user) * 3 + attempt(sso_login_flow, page)
page = plan(delay=0.5, catch=(TimeoutError,))
```
