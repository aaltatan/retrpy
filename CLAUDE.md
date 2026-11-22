# CLAUDE.md

## Project

A small, zero-dependency Python package for the **retry + fallback pattern**, expressed as
**plans of steps** composed with ordinary Python operators. Inspired by the final version in
ArjanCodes' *Retry Pattern: The Secret to Resilient Python Code*.

Package name: **TBD** (it may also end up as part of `pyflowstep`; see Open decisions).

## Core idea

A `Plan[T]` is an immutable, ordered tuple of zero-argument callables (steps).
Running a plan calls each step in turn and **the first one that succeeds wins**.

- Retry is **repetition**: `attempt(...) * 3`
- Fallback is **concatenation**: `primary * 3 + backup * 2`
- A default value is **just one more step**: `+ attempt(lambda: None)`, which widens the type to `Plan[T | None]`
- A plan is a **value**: build it first, run it later. It supports `len()` and can be passed around and composed.

Target usage:

```python
plan = (
    attempt(fetch_rate, client, primary_url) * 3
    + attempt(fetch_rate, client, backup_url) * 2
    + attempt(lambda: None)
)
rate = plan(delay=0.05, backoff=2.0, catch=(NetworkError, RetryableHTTPError))
```

## Design principles

- **Python syntax first.** Prefer operators and built-in protocols (`*`, `+`, `len`, `__call__`,
  iteration) over new methods or a builder DSL. Operators should behave the way the same
  operators behave on tuples, unless there's a stated reason not to.
- **Functional.** Plans are immutable values. No hidden state and no mutation. Functions
  and closures are preferred over class hierarchies.
- **Exceptions are the only failure signal.** Retry-on-result is done by having the step
  validate and raise, e.g. turning HTTP 429/5xx into `RetryableHTTPError`. Don't add
  result predicates.
- **Errors outside `catch` fail fast.** They propagate immediately and are never wrapped.
- **Never catch `BaseException`.** `KeyboardInterrupt` and `asyncio.CancelledError` always propagate.
- **Side effects are injectable.** `sleep` (and later the clock and RNG) are parameters, so
  tests run instantly and deterministically.
- **Small surface.** Every new public name has to justify itself. If a plain function or
  lambda does the job, don't add a helper.

## Known issues in the reference version (to address)

1. **Backoff counts across the whole plan.** `delay * backoff**i` uses the position in the
   whole plan, so the backup source inherits the primary's grown delay. Backoff should
   probably restart per repeated segment, with no wait (or a separate wait) when switching
   source.
2. **Settings apply to every step.** `delay`, `backoff` and `catch` are given only at call
   time. Consider letting segments carry their own settings, with call-time values as defaults.
3. **Failure history is lost.** Only the last exception surfaces. Options: raise an
   `ExceptionGroup` (so callers can use `except*`), or `add_note()` an attempt summary to the
   last exception.
4. Remove the `AssertionError("Unreachable")` by handling the last step outside the loop.
5. `__mul__` returns `Self` but `__add__` returns `Plan`. Make subclass behaviour consistent.
6. Keep rejecting `* 0` and negative counts, even though tuples allow them.

## Open decisions (ask before choosing)

- Standalone package, or part of `pyflowstep`?
- Backoff per segment or for the whole plan (issue 1)?
- Where settings live: call time only, per segment, or both (issue 2)?
- Exhausted-plan error: `ExceptionGroup` or last exception with notes (issue 3)?
- Async: a separate `AsyncPlan`, or one plan with sync and async runners?
- Extras: a jitter function, a max-delay cap, an `on_failure` hook for logging, a fixed-value step helper.

## Conventions

- Python **3.12+**. Use PEP 695 generics (`class Plan[T]`, `def attempt[T, **P]`) and `type` aliases.
- `@dataclass(frozen=True, slots=True)` for value types.
- Full type hints, `mypy --strict` clean, `py.typed` shipped.
- `ruff` for lint and format, line length 100.
- `src/` layout, `pyproject.toml` with hatchling, no runtime dependencies.
- Tests with `pytest`, using a fake `sleep` and scripted fake clients (like `FakeClient` in the
  reference). Never sleep for real in tests.
- Public API re-exported from `__init__.py` with an explicit `__all__`.
- Docstrings explain the *why* and the semantics; examples go in the README.

## Workflow

- Discuss the design before implementing anything that touches an open decision.
- Keep changes small. Each one gets tests for the success path, the retry path, the fallback
  path and fail-fast.
- Run `pytest` and `mypy` before calling work done.
