# retrpy

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

## Install

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

## Testing

Pass a fake `sleep` so tests run instantly and you can assert on the waits:

```python
waits = []
plan(delay=0.05, backoff=2.0, sleep=waits.append)
assert waits == [0.05, 0.1]
```

## With pyflowstep

A pyflowstep `Flow` is a callable, so it can be an attempt as is:

```python
plan = attempt(login_flow, page, user=user) * 3 + attempt(sso_login_flow, page)
page = plan(delay=0.5, catch=(TimeoutError,))
```
