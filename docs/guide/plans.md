# Building plans

| Expression | Meaning |
| --- | --- |
| `attempt(fn, *args, **kwargs)` | one attempt of `fn(*args, **kwargs)` |
| `p * n` or `n * p` | retry: repeat `n` times (`n >= 1`) |
| `p + q` | fallback: run `q`'s attempts after `p`'s |
| `+ attempt(lambda: default)` | a default value is just one more attempt |
| `len(p)` | the number of attempts |
| `iter(p)` | the attempts, as zero-argument callables |

## One attempt

`attempt` takes any callable and the arguments to call it with. Nothing runs until the plan
is called.

```python
from retrpy import attempt

plan = attempt(int, "ff", base=16)

assert len(plan) == 1
assert plan() == 255
```

The callable is positional-only, so its own keyword arguments never clash with `attempt`'s.
Type checkers check `args` and `kwargs` against the callable's signature, and the plan's
result type is the callable's return type.

## Retry is repetition

```python
from retrpy import attempt

plan = attempt(int, "7") * 3

assert len(plan) == 3
assert len(3 * attempt(int, "7")) == 3
```

The count must be an `int` of at least 1. `* 0` and negative counts raise `ValueError`,
even though tuples allow them: an empty plan can't return anything.

```python
import pytest

from retrpy import attempt

with pytest.raises(ValueError, match="at least 1"):
    attempt(int, "7") * 0
```

## Fallback is concatenation

`+` runs the right plan's attempts after the left plan's. The result type widens to the
union of both sides, so a `Plan[float] + Plan[None]` is a `Plan[float | None]`.

```python
from retrpy import attempt


def from_api() -> float:
    raise ConnectionError("down")


def from_cache() -> float:
    return 1.08


plan = attempt(from_api) * 3 + attempt(from_cache)

assert len(plan) == 4
assert plan(catch=(ConnectionError,)) == 1.08
```

## A default value is one more attempt

```python
from retrpy import attempt


def lookup() -> str:
    raise LookupError("missing")


plan = attempt(lookup) * 2 + attempt(lambda: "anonymous")

assert plan(catch=(LookupError,)) == "anonymous"
```

## Operators behave like they do on tuples

Multiplying a plan of one segment grows that segment, so `(a * 2) * 3` is six attempts of
`a` with one continuous backoff. Multiplying a plan of several segments repeats the whole
sequence, so `(a + b) * 3` rotates `a, b, a, b, a, b`.

```python
from retrpy import attempt

seen = []


def source(name: str) -> None:
    seen.append(name)
    raise ConnectionError(name)


rotation = (attempt(source, "a") + attempt(source, "b")) * 3

try:
    rotation(catch=(ConnectionError,))
except ExceptionGroup:
    pass

assert seen == ["a", "b", "a", "b", "a", "b"]
assert len((attempt(source, "a") * 2) * 3) == 6
```

!!! note "Segments decide where backoff restarts"
    `attempt(a) * 6` is one segment: the wait keeps growing across all six tries.
    `attempt(a) * 3 + attempt(a) * 3` is two segments: the wait restarts after the third
    try. See [Waits, backoff and jitter](waits.md).

## Plans are values

Since plans are immutable values, ordinary Python builds them: name fragments, reduce a list
of sources, store a policy in a module and import it.

```python
from functools import reduce
from operator import add

from retrpy import attempt

MIRRORS = ["https://a.example.com", "https://b.example.com", "https://c.example.com"]


def fetch(url: str) -> str:
    return url


plan = reduce(add, (attempt(fetch, url) * 2 for url in MIRRORS))

assert len(plan) == 6
assert plan() == "https://a.example.com"
```

Iterating a plan yields each attempt as a zero-argument callable, in the order they run:

```python
from retrpy import attempt

plan = attempt(int, "1") * 2 + attempt(int, "2")

assert [step() for step in plan] == [1, 1, 2]
```
