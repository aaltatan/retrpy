# retrpy

**Retry and fallback as plans of attempts, composed with ordinary Python operators.**

Zero dependencies, fully typed. Retry is repetition (`* 3`), fallback is concatenation
(`+`), and a default value is just one more attempt.

```py
plan = (
    attempt(fetch_rate, PRIMARY, "USD", "EUR") * 3  # try the primary 3 times
    + attempt(fetch_rate, BACKUP, "USD", "EUR") * 2  # then the backup twice
    + attempt(lambda: None)  # then give up with None
)
rate = plan(delay=0.5, backoff=2.0, catch=(TimeoutError, ConnectionError))
```

A plan is a value: build it once, run it as often as you like, pass it around, `len()` it.
The first attempt that succeeds wins.

## A first taste

A flaky service fails twice, then answers. A fake `sleep` records the waits instead of
sleeping, so this runs instantly.

```python
from retrpy import attempt

calls = []


def flaky_service() -> str:
    calls.append(1)

    if len(calls) < 3:
        raise ConnectionError("try again")

    return "ok"


waits = []
plan = attempt(flaky_service) * 5

assert len(plan) == 5
assert plan(delay=0.1, backoff=2.0, catch=(ConnectionError,), sleep=waits.append) == "ok"
assert len(calls) == 3
assert waits == [0.1, 0.2]
```

## Why not a hand-written loop?

A nightly job converts order totals from USD to EUR. The rate provider sometimes times out.
You want: retry the main provider with a growing wait, switch to a backup, and as a last
resort use yesterday's rate. Written by hand, that loop tends to grow quiet bugs:

- the backup inherits the primary's grown wait instead of starting fresh;
- it sleeps for nothing before switching source;
- only the last error survives;
- `time.sleep` is hard-wired, so the tests really sleep.

With retrpy each of those is handled by the plan itself:

- **Each source gets its own backoff**, and there is no wait when switching source.
- **Bugs fail fast.** An error that isn't in `catch` surfaces on the first try, unwrapped.
- **Nothing is lost.** When every attempt fails you get one `ExceptionGroup` with every
  failure, in order.
- **Tests are instant.** Pass `sleep=waits.append` and assert on the waits.
- **The policy is a value.** Import it, reuse it, extend it with `+`.

## Where to next

<div class="grid cards" markdown>

- [**Installation**](install.md): one command.
- [**User guide**](guide/index.md): every feature, one page each.
- [**Recipes**](recipes.md): complete real-world programs.
- [**API reference**](reference/api.md): every parameter and its default.

</div>
