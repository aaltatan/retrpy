# retrpy core: design

Date: 2026-11-22. Size: small project (one module, tests, README).

## Intent

A zero-dependency library for the retry + fallback pattern, where a plan of attempts is an
immutable value composed with ordinary operators: `*` retries, `+` falls back, and a default
is one more attempt. It fixes the known issues in ArjanCodes' final version, listed in
CLAUDE.md.

```python
plan = (
    attempt(fetch_rate, client, primary_url) * 3
    + attempt(fetch_rate, client, backup_url) * 2
    + attempt(lambda: None)
)
rate = plan(delay=0.05, backoff=2.0, catch=(NetworkError, RetryableHTTPError))
```

## Goals, non-goals, anti-goals

- **Goals:** operators that behave like tuple operators; deterministic tests through an
  injectable `sleep`; the full failure history kept; `mypy --strict` clean; `py.typed`.
- **Non-goals in v1:** async, per-segment settings, result predicates, any integration with
  pyflowstep.
- **Anti-goals:** catching `BaseException`; wrapping errors outside `catch`; a builder DSL;
  runtime dependencies; any name that clashes with pyflowstep's API.

## Approaches considered

| Decision | Options | Picked |
| --- | --- | --- |
| Backoff | whole plan (reference) / restart per segment / restart + switch wait | **restart per segment, no wait on switch** |
| Settings | call time only / per segment / both | **call time only** |
| Exhausted error | `ExceptionGroup` / last exception + notes | **`ExceptionGroup`** |
| Segment rules | tuple-like / merge equal neighbours / only `step * n` | **tuple-like, never merge** |
| Internals | tuple of segments / flat steps + indexes / tree | **tuple of segments** |
| Extras API | plain callables / jitter flag + rng | **plain callables** |
| Packaging | standalone hatchling / uv_build / in pyflowstep | **standalone `retrpy`, hatchling** |
| Async | defer / `AsyncPlan` / two runners | **defer** |

Tuple of segments won because the segment is the unit backoff works on; the flat form needs
two tuples kept in sync, and a tree is more general than flattening semantics need.
The pyflowstep question was settled by an independent report
(`docs/reports/2026-11-22-pyflowstep-integration.md`): a pyflowstep `Flow` is already a
callable, so `attempt(flow, page) * 3` composes the two with no new code.

## Decided design

**Public API:** `Plan` and `attempt`, re-exported with `__all__`. `step` was renamed to
`attempt` to avoid clashing with pyflowstep's `step`.

**Values.**

```python
@dataclass(frozen=True, slots=True)
class Segment[T]:          # internal, readable via plan.segments
    fn: Callable[[], T]
    count: int

@dataclass(frozen=True, slots=True)
class Plan[T]:
    segments: tuple[Segment[T], ...]

def attempt[T, **P](fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Plan[T]: ...
```

`attempt` binds the arguments and returns a one-segment plan with `count=1`.
`len(plan)` is the total number of attempts. Iterating yields each attempt's callable,
expanded.

**Operators** (tuple-like; both return `type(self)`):

- `plan * n`: a one-segment plan multiplies its count, so `(a*2)*3` is `[a x6]`. Any other
  plan repeats the whole sequence, so `(a*2 + b)*3` is
  `[a x2][b x1][a x2][b x1][a x2][b x1]`.
- `n * plan` behaves the same (`__rmul__`).
- `plan + other` concatenates segments and never merges, so `a*2 + a*3` is `[a x2][a x3]`.
  `Plan[T] + Plan[U]` gives `Plan[T | U]`.
- `n` that is not an `int` returns `NotImplemented`; `n < 1` raises `ValueError`.

**Running.**

```python
def __call__(
    self, *,
    delay: float = 0.0,
    backoff: float = 1.0,
    catch: tuple[type[Exception], ...] = (Exception,),
    max_delay: float | None = None,
    jitter: Callable[[float], float] | None = None,
    on_failure: Callable[[Exception, int], None] | None = None,
    sleep: Callable[[float], object] = time.sleep,
) -> T: ...
```

- Attempts run in order, and the first success returns its value.
- An exception not in `catch` propagates immediately, unwrapped. `catch` may only hold
  `Exception` subclasses, so `KeyboardInterrupt` and similar always propagate.
- After a caught failure, the next attempt in the **same segment** waits
  `delay * backoff**k` (k = 0, 1, … restarting at each segment), then `jitter` is applied,
  then the result is capped by `max_delay`. There is no wait between segments. A wait of
  zero or less skips the `sleep` call.
- `on_failure(exc, attempt_number)` is called for every caught failure, 1-based across the
  whole plan, including the last one.
- When every attempt fails, it raises `ExceptionGroup(f"all {n} attempts failed", errors)`
  in attempt order. No unreachable `AssertionError`.
- Calling an empty plan raises `ValueError`.

## Calls I made (check these)

1. Defaults: `delay=0`, `backoff=1`, `catch=(Exception,)`, others `None`, `sleep=time.sleep`.
2. `on_failure` also runs for the final failure.
3. A wait of zero or less doesn't call `sleep`, so tests can tell which attempts waited.
4. `__rmul__` is supported, because tuples support `3 * t`.
5. Run settings are keyword-only.
6. Validation of `delay`, `backoff` and `max_delay` values is left out; negative values just
   mean no wait.

## Left to the builder

Module layout (a single `src/retrpy/_plan.py` is enough), docstring wording, README examples,
the exact test list (each feature gets success, retry, fallback and fail-fast tests with a
fake `sleep` and a scripted fake client), and fixing `pyproject.toml`: hatchling, no
console script, `py.typed`.
