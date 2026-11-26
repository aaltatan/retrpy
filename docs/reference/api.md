# API

`T` is the type an attempt returns.

## `attempt`

```py
attempt(fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Plan[T]
```

Bind `fn` to its arguments as a plan of one attempt, ready for `*` and `+`. `fn` is
positional-only; `args` and `kwargs` are type-checked against its signature. Nothing is
called until the plan runs.

Guide: [Building plans](../guide/plans.md).

## `Plan[T]`

```py
@dataclass(frozen=True, slots=True)
class Plan[T]:
    segments: tuple[Segment[T], ...]
```

An immutable, ordered sequence of attempts; the first one that succeeds wins. A plan keeps
**segments** (one callable repeated `count` times) rather than a flat list, because the wait
grows within a segment and restarts at the next one. Build plans with `attempt`, `*` and
`+`; you rarely construct one directly.

| Member | Description |
| --- | --- |
| `plan * n`, `n * plan` | new plan repeated `n` times; `n` must be an `int >= 1`. A one-segment plan grows its count; a multi-segment plan repeats its segments like a tuple |
| `plan + other` | new `Plan[T \| U]` with `other`'s attempts after `plan`'s |
| `len(plan)` | total number of attempts |
| `iter(plan)` | each attempt as a zero-argument callable, in run order |
| `plan(...)` | run it; see below |

Operators keep the subclass of the left-hand plan. Using `*` with a non-`int` or `+` with a
non-`Plan` raises `TypeError`.

### Running: `plan(...)`

```py
plan(
    *,
    delay: float = 0.0,
    backoff: float = 1.0,
    catch: tuple[type[Exception], ...] = (Exception,),
    max_delay: float | None = None,
    jitter: Callable[[float], float] | None = None,
    on_failure: Callable[[Exception, int], None] | None = None,
    sleep: Callable[[float], object] = time.sleep,
) -> T
```

Run the attempts in order and return the first success.

| Parameter | Description |
| --- | --- |
| `delay` | first wait between two tries of a segment, in seconds |
| `backoff` | each next wait in the same segment is multiplied by this |
| `catch` | the `Exception` subclasses treated as retryable failures; others propagate at once, unwrapped |
| `max_delay` | cap on a single wait, applied after `jitter` |
| `jitter` | maps each computed wait to the one to use |
| `on_failure` | called as `on_failure(error, number)` for every caught failure, numbered from 1 across the plan, including the last |
| `sleep` | called with each positive wait; inject a fake in tests |

The wait after try `k` (from 0) of a segment is `delay * backoff**k`, then `jitter`, then
`max_delay`. There is no wait after the last try of a segment, so switching to the next
segment is immediate. A wait of zero or less skips `sleep`. A wait too big for a float
becomes `inf` instead of raising `OverflowError`.

Raises: see [Exceptions](exceptions.md).

Guide: [Running a plan](../guide/running.md), [Waits](../guide/waits.md),
[When everything fails](../guide/failures.md).
