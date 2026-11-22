# retrpy core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship retrpy v1: an immutable `Plan[T]` of retryable attempts composed with `*` and `+`,
run with call-time settings, raising `ExceptionGroup` when exhausted.

**Architecture:** One module `src/retrpy/_plan.py` holds `Segment`, `Plan` and `attempt`.
`__init__.py` re-exports `Plan` and `attempt`. A plan is a tuple of `(fn, count)` segments, and
backoff restarts per segment.

**Tech Stack:** Python 3.12+, hatchling, pytest, mypy --strict, ruff (line length 100). No
runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-11-22-retrpy-core-design.md`

## Global Constraints

- Python `>=3.12`; PEP 695 generics; `@dataclass(frozen=True, slots=True)` for values.
- No runtime dependencies. Build backend `hatchling`. No `[project.scripts]`. Ship `py.typed`.
- Public API exactly `__all__ = ["Plan", "attempt"]`. Never export or use the name `step`.
- Never catch `BaseException`; errors outside `catch` propagate unwrapped.
- Tests never sleep for real: pass a fake `sleep` that records delays.
- Code style: blank line before every `return` and around every block (user's global rule).
- `uv run pytest`, `uv run mypy --strict src tests`, `uvx ruff check .` and
  `uvx ruff format --check .` must pass before any task is done.

## Review Focus

1. `KeyboardInterrupt` raised by an attempt with the default `catch=(Exception,)` must propagate
   immediately, with no retry and no `on_failure` call (test in Task 3).
2. An exception raised by `on_failure` itself propagates as-is and stops the run (test in Task 4).
3. `jitter` returning a negative or zero value means no `sleep` call, not `sleep(-x)` (test in
   Task 4).
4. `plan + 3` and `plan * 2.0` raise `TypeError` through `NotImplemented`, not `AttributeError`
   (test in Task 2).
5. The run is stateless: calling the same plan twice gives two independent runs, and backoff
   doesn't carry over (test in Task 3).

---

### Task 1: Packaging and the `Plan` value

**Files:**
- Modify: `pyproject.toml`
- Create: `src/retrpy/_plan.py`, `src/retrpy/py.typed` (empty)
- Modify: `src/retrpy/__init__.py` (replace the hello-world `main`)
- Test: `tests/test_plan.py`

**Interfaces:**
- Produces: `Segment[T](fn: Callable[[], T], count: int)`, `Plan[T](segments: tuple[Segment[T], ...])`,
  `attempt[T, **P](fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Plan[T]`,
  `Plan.__len__() -> int`, `Plan.__iter__() -> Iterator[Callable[[], T]]`.

- [ ] **Step 1: Fix `pyproject.toml`.** Set `build-backend = "hatchling.build"` with
  `requires = ["hatchling"]`, set a real `description`, delete `[project.scripts]`, add
  `[dependency-groups] dev = ["pytest", "mypy", "ruff"]`, add
  `[tool.ruff] line-length = 100, target-version = "py312"` and
  `[tool.mypy] strict = true`. Run `uv sync`. Expected: installs without errors.

- [ ] **Step 2: Write failing tests** in `tests/test_plan.py`, `class TestAttempt`:

```python
def test_binds_arguments(self):
    plan = attempt(pow, 2, exp=3)
    assert len(plan.segments) == 1
    assert plan.segments[0].count == 1
    assert plan.segments[0].fn() == 8

def test_len_and_iter_expand_counts(self):
    plan = Plan((Segment(lambda: 1, 2), Segment(lambda: 2, 1)))
    assert len(plan) == 3
    assert [f() for f in plan] == [1, 1, 2]

def test_is_immutable(self):
    with pytest.raises(dataclasses.FrozenInstanceError):
        attempt(int).segments = ()  # type: ignore[misc]

def test_public_api(self):
    assert retrpy.__all__ == ["Plan", "attempt"]
```

- [ ] **Step 3:** Run `uv run pytest tests/test_plan.py -v`. Expected: FAIL (import errors).
- [ ] **Step 4:** Implement the interfaces above in `_plan.py`. `attempt` uses
  `functools.partial`. Re-export from `__init__.py`.
- [ ] **Step 5:** Run pytest + mypy + ruff (Global Constraints). Expected: all pass.
- [ ] **Step 6: Commit** `feat: add Plan value and attempt`.

### Task 2: Operators

**Files:** Modify `src/retrpy/_plan.py`; Test `tests/test_operators.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `Plan.__mul__(n: int) -> Self`, `Plan.__rmul__(n: int) -> Self`,
  `Plan.__add__[U](other: Plan[U]) -> Plan[T | U]`.

- [ ] **Step 1: Write failing tests** (`a = attempt(f)`, `b = attempt(g)`, compare by
  `[(s.fn, s.count) for s in plan.segments]`):
  - `test_mul_single_segment_multiplies_count`: `(a * 2) * 3` gives `[(f_a, 6)]`.
  - `test_rmul_matches_mul`: `3 * a == a * 3`.
  - `test_mul_multi_segment_repeats_sequence`: `(a * 2 + b) * 3` gives
    `[(fa, 2), (fb, 1)] * 3`.
  - `test_add_never_merges`: `a * 2 + a * 3` gives `[(fa, 2), (fa, 3)]`.
  - `test_mul_rejects_zero_and_negative`: `pytest.raises(ValueError, match="at least 1")` for
    `a * 0` and `a * -1`.
  - `test_wrong_operand_types_raise_type_error`: `a + 3`, `a * 2.0` raise `TypeError`.
  - `test_subclass_preserved`: `class P(Plan): ...`; `type(P(a.segments) * 2) is P` and
    `type(P(a.segments) + b) is P`.
- [ ] **Step 2:** Run `uv run pytest tests/test_operators.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** A non-`int` operand returns `NotImplemented`. Use
  `dataclasses.replace(self, segments=...)` so subclasses are kept. Error message:
  `f"Plan can only be repeated at least 1 time, got {n}"`.
- [ ] **Step 4:** Run the full checks. Expected: all pass.
- [ ] **Step 5: Commit** `feat: add tuple-like * and + to Plan`.

### Task 3: Running: success, retry, fallback, fail fast, exhaustion

**Files:** Modify `src/retrpy/_plan.py`; Create `tests/conftest.py`; Test `tests/test_run.py`

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: `Plan.__call__(self, *, delay: float = 0.0, backoff: float = 1.0, catch:
  tuple[type[Exception], ...] = (Exception,), sleep: Callable[[float], object] = time.sleep)
  -> T`. Task 4 adds the remaining keywords.
- Fixtures in `conftest.py`: `FakeSleep` (callable, records `.calls: list[float]`), and
  `Scripted(*outcomes)`, a callable that returns or raises each outcome in turn and counts
  `.calls`. Expose both as fixtures/factories.

- [ ] **Step 1: Write failing tests:**
  - `test_success_first_try`: returns the value, `sleep.calls == []`.
  - `test_retry_then_success`: `Scripted(E(), E(), 7)` as `attempt(s) * 3`, with `delay=0.05,
    backoff=2.0`, returns 7 and `sleep.calls == [0.05, 0.1]`.
  - `test_fallback_backoff_restarts_per_segment`: primary always fails `* 3`, backup
    `Scripted(E(), 9) * 2`, `delay=0.05, backoff=2.0` gives `sleep.calls == [0.05, 0.1, 0.05]`.
  - `test_default_value_step`: `attempt(failing) * 2 + attempt(lambda: None)` returns `None`.
  - `test_fail_fast_outside_catch`: raising `ValueError` with `catch=(KeyError,)` propagates the
    same object (`excinfo.value is err`) after one call.
  - `test_keyboard_interrupt_propagates`: an attempt raising `KeyboardInterrupt` under the
    default catch propagates after one call.
  - `test_exhausted_raises_exception_group`: 3 failures give
    `ExceptionGroup` with message `"all 3 attempts failed"` and `.exceptions` equal to the three
    errors in order.
  - `test_empty_plan_raises`: `Plan(())()` raises `ValueError`.
  - `test_runs_are_independent`: the same plan called twice records the same `sleep.calls`
    each time.
  - `test_zero_delay_never_sleeps`: `delay=0` with retries gives `sleep.calls == []`.
- [ ] **Step 2:** Run `uv run pytest tests/test_run.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `__call__`.** Loop over segments, then over `range(count)`. Track `k`
  per segment. Collect errors in a list, sleep only between attempts of the same segment and
  only when the wait is `> 0`. After the loop, raise the group. There is no unreachable branch.
- [ ] **Step 4:** Run the full checks. Expected: all pass.
- [ ] **Step 5: Commit** `feat: run plans with per-segment backoff and ExceptionGroup`.

### Task 4: Extras: jitter, max_delay, on_failure

**Files:** Modify `src/retrpy/_plan.py`; Test `tests/test_extras.py`

**Interfaces:**
- Consumes: Task 3 `__call__`.
- Produces: extra keywords `max_delay: float | None = None`,
  `jitter: Callable[[float], float] | None = None`,
  `on_failure: Callable[[Exception, int], None] | None = None`.
  Order: `wait = delay * backoff**k`, then `jitter(wait)`, then `min(wait, max_delay)`.

- [ ] **Step 1: Write failing tests:**
  - `test_jitter_applied`: `jitter=lambda d: d / 2`, `delay=0.1`, gives `sleep.calls == [0.05]`.
  - `test_max_delay_caps_after_jitter`: `delay=1, backoff=10, jitter=lambda d: d + 1,
    max_delay=5` over 3 tries gives `[2, 5]`.
  - `test_nonpositive_jitter_skips_sleep`: `jitter=lambda d: -1` gives `sleep.calls == []`.
  - `test_on_failure_every_caught_failure_including_last`: all 3 fail gives calls
    `[(e1, 1), (e2, 2), (e3, 3)]`, then `ExceptionGroup`.
  - `test_on_failure_numbers_across_segments`: `a*2 + b` failing gives numbers `[1, 2, 3]`.
  - `test_on_failure_not_called_for_fail_fast`: an uncaught error gives no calls.
  - `test_on_failure_error_propagates`: a hook raising `RuntimeError` stops the run with that
    `RuntimeError`.
- [ ] **Step 2:** Run `uv run pytest tests/test_extras.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the three keywords in `__call__`. Put the wait computation in a
  private helper `_wait(delay, backoff, k, jitter, max_delay) -> float` below the public code.
- [ ] **Step 4:** Run the full checks. Expected: all pass.
- [ ] **Step 5: Commit** `feat: add jitter, max_delay and on_failure`.

### Task 5: Docs

**Files:** Modify `README.md`, `src/retrpy/_plan.py` docstrings

- [ ] **Step 1:** README: install, the target example, operator table (`* n`, `+`, default
  value), run keywords with defaults, `except*` example, a test example with a fake `sleep`,
  and using it with a pyflowstep `Flow` via `attempt(flow, page) * 3`.
- [ ] **Step 2:** Docstrings on `Plan`, `attempt` and `__call__` explain the semantics and the
  *why* (per-segment backoff, never `BaseException`). Examples stay in the README.
- [ ] **Step 3:** Run the full checks. Expected: all pass.
- [ ] **Step 4: Commit** `docs: README and docstrings`.
