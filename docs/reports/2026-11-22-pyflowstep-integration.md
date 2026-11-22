# Should retrpy be built into pyflowstep?

Date: 2026-11-22. Read-only review of pyflowstep 0.8.0 and the agreed retrpy design.
Paths below are relative to `python-packages/`.

## 1. How pyflowstep works today

- **Core value.** `Flow[T]` is an immutable sequence of actions, each `T -> T`
  (`pyflowstep/src/pyflowstep/flow.py:10`, `:13`). It is a plain `__slots__` class, not a
  dataclass (`flow.py:44`).
- **A step** is a function `(subject, *args, **kwargs) -> subject`. `@step` turns it into a
  *factory*: calling `click("#go")` binds and validates the arguments at build time and returns
  a one-action `Flow` (`steps.py:67`, `steps.py:339-353`). `tap` and `output` are variants
  (`steps.py:103`, `:126`); `chain` names a function that returns a flow (`steps.py:226`).
- **`>>`** accepts any callable and returns a new, flat `Flow` (`flow.py:101-109`, flattening at
  `flow.py:165`). There is no `*` or `+`.
- **Running.** `flow(subject, **inputs)` opens a run scope, checks every required `Input` before
  the first step, then folds the subject through the actions (`flow.py:62-65`). A run scope caches
  `Depends` providers once per run and cleans up generator providers at the end
  (`dependencies.py:166-195`). A nested flow call *joins* the open run (`dependencies.py:179-182`).
- **Inputs and outputs** are found by reading marker attributes on each action
  (`inputs.py:47-48`, `:177`, `:215`, `:225`, `:273`).
- **Errors.** One base `PyflowstepError`, with specific subclasses that also derive from
  `TypeError` or `ValueError` (`exceptions.py:18-110`). Errors raised by step bodies at run time
  pass through untouched; pyflowstep only owns build-time errors. JSON path context is added as a
  note via `pyvocabulary.located`, never by wrapping (`compilers.py:95`, rule in
  `pyflowstep/CLAUDE.md`).
- **JSON, registry, schema.** `FlowCompiler` turns `[{"name", "args", "kwargs"}, ...]` into a
  flat flow by looking names up in a mapping of factories, usually `StepsRegistry.steps`
  (`compilers.py:33-103`). JSON Schema is generated from factory signatures
  (`json_schema.py:45`, `:74`). The definition format is a *flat list*: there is no nesting.
- **Rules that matter here** (`pyflowstep/CLAUDE.md`): validate when built, not when run; ask
  before adding a runtime dependency; no feature or layer nobody asked for. pyflowstep already
  depends on `pyargprocessors` and `pyvocabulary` (`pyflowstep/pyproject.toml:11-14`).

## 2. Fit analysis

**Where it maps.** A `Flow` is a callable, and retrpy's `attempt(fn, *args, **kwargs)` binds
arguments. So a flow can already be a retrpy attempt, with no glue:

```python
login = fill_user() >> click("#login")                  # Flow[Page], `user` is an Input
plan = attempt(login, page, user=u) * 3 + attempt(sso_login, page)
page = plan(delay=0.5, catch=(TimeoutError,))
```

retrpy's "first success wins" also echoes pyruleset's "first match wins"
(`pyruleset/src/pyruleset/ruleset.py:45`), so the family already has an ordered-alternatives idea.

**Where it clashes.**

| Tension | Detail |
|---|---|
| Shape | retrpy steps are `() -> T`; pyflowstep actions are `T -> T`. A retry *inside* a flow must become `T -> T`, so the subject is bound per run, not at build time. |
| Operators | On a `Flow`, tuple-like `*` would naturally mean "run the steps N times in a row", not "retry". `+` would duplicate `>>`. Putting `*`/`+` on `Flow` breaks retrpy's own rule that operators behave like tuples. |
| Mutable subjects | Many subjects are mutated in place (`tap` exists for that, `steps.py:103`). A failed attempt can leave a `Page` half-filled; the retry starts from that state, not a clean one. Only the step author can fix this. |
| Run scope | A retry inside a run joins the same scope: a cached `Depends` object (a broken session, say) is reused by every attempt, and an `output` written by a failed attempt stays visible. |
| Hidden inputs | If a retry wraps a sub-flow into one action, `flow.inputs`, `check_inputs` and `Flow.signature` no longer see the sub-flow's `Input`s and `output`s unless the wrapper copies the markers. |
| Dependencies | retrpy is meant to have zero dependencies; inside pyflowstep it inherits two. pyflowstep importing retrpy adds a third, which needs the author's approval. |
| Injectable `sleep` | Fine at call time. Inside a compiled flow there is no call site, so `sleep` would have to be a `Depends` provider (overridable with `override_dependencies` in tests). |
| Errors | `ExceptionGroup` is a run-time outcome, not a definition error, so it need not be a `PyflowstepError`. But a group is a *wrapper*, which pyflowstep's "never wrap" rule avoids. Acceptable, but a new kind of error flows would raise. |
| Build-time validation | retrpy validates counts at build time but `delay`/`catch` only at call time. For a retry step in a JSON flow those settings must be fixed when the flow is built: the opposite of the agreed "call-time only" decision. |
| JSON | `catch` is a tuple of classes, which JSON cannot hold; it needs a name-to-exception registry. Fallback needs *nested* flows, which the flat `StepDict` list cannot express. |

## 3. Options

### (a) Standalone retrpy; pyflowstep unchanged

```python
from retrpy import attempt
plan = attempt(checkout, page, user=u) * 3 + attempt(checkout_slow, page, user=u)
plan(delay=1, backoff=2, catch=(TimeoutError,))
```

- pyflowstep changes: none. Optionally one README section, "Retrying a flow".
- retrpy design: survives intact (zero deps, call-time settings, `ExceptionGroup`).
- Effort: lowest. Limits: retry only *around* whole flows, not *inside* one; not in JSON.
- No name clash: retrpy exports `attempt`, pyflowstep `step`. Semver: no change.

### (b) A retry combinator inside pyflowstep

A factory that turns flows into one `T -> T` action, with settings bound at build time:

```python
flow = open_form() >> retry(fill_and_save(), times=3, delay=0.5,
                            catch=(TimeoutError,)) >> close()
flow = open_form() >> fallback(api_save(), ui_save()) >> close()
```

- pyflowstep changes: a new `retry.py` (or `retry`/`fallback` next to `compose` in `flow.py`),
  marker copying so inputs and outputs stay correct (`inputs.py`), exports in `__init__.py`,
  README, tests. For JSON: either one registered `chain` per use, or a nested `StepDict` form in
  `compilers.py` with schema changes in `json_schema.py`, plus an exception-name registry.
- retrpy design: operators and call-time settings are lost; segments, per-segment backoff,
  jitter and cap, `on_failure` and `ExceptionGroup` survive as the engine. It could import retrpy
  (new dependency) or reimplement about 60 lines.
- Effort: medium without JSON, high with it. Risks: run-scope reuse and mutable subjects (above);
  a second retry model next to retrpy's. Semver: additive, minor (0.9.0).

### (c) retrpy as a family member (registry, compiler, schema)

`Plan` gets a `PlanCompiler`, a vocabulary of named attempts, and JSON like
`[{"name": "fetch_rate", "args": [...], "times": 3}, ...]`, built on pyvocabulary.

- pyflowstep changes: none.
- retrpy design: the core survives, but zero deps goes (pyvocabulary), and the JSON form puts
  settings and `catch` into the definition, reopening the "call time only" decision.
- Effort: high. Risk: building a compiler before anyone needs retry plans from JSON; the family
  rule is "no abstraction until a second real use exists". Semver: none for pyflowstep.

### (d) Merge wholesale into pyflowstep

`Plan`, `Segment` and the runner move into pyflowstep, possibly with `*`/`+` on `Flow`.

- pyflowstep changes: a new module, exports, possibly new `Flow` operators.
- retrpy design: zero deps lost; `() -> T` plans sit beside `T -> T` flows, two kinds of building
  block (`attempt` and `step`) in one package; `*` on `Flow` contradicts tuple semantics.
- Effort: medium. Risk: highest. It grows a released API with a concept that does not share its
  core shape, and is hard to undo. Semver: minor bump, but a permanent surface.

### Summary

| | pyflowstep change | retrpy design kept | Effort | Risk |
|---|---|---|---|---|
| (a) standalone | none | all | low | low |
| (b) combinator | additive | engine only | medium to high | medium |
| (c) family member | none | most, minus zero deps | high | medium |
| (d) merge | large | partial | medium | high |

## 4. Recommendation

**Build retrpy standalone (option a) and do not change pyflowstep now.**

- The two values have different shapes (`() -> T` vs `T -> T`) and different algebras
  (repetition and concatenation vs sequencing). Forcing either onto the other costs the clarity
  that is the point of both.
- Interop is already free: a `Flow` is a callable, so `attempt(flow, subject, **inputs) * 3` works
  today, and each attempt opens a fresh run scope, which avoids the scope-reuse problem.
- It keeps every decision already agreed for retrpy (zero deps, call-time settings,
  `ExceptionGroup`) and adds nothing to pyflowstep's released API.
- If a real need appears for retry *inside* a flow, or in a JSON flow, add option (b) later as an
  additive pyflowstep feature with retrpy as its engine. That is a minor release and loses nothing
  done now. Meanwhile, document the flow-in-a-plan pattern in retrpy's README.

## Open questions for the author

1. Is there a concrete use for retry *inside* a flow (one step retried mid-flow), or is retrying
   whole flows enough?
2. Must retry or fallback be expressible in JSON/TOML flow files? This is the main thing that
   would justify (b) or (c).
3. May pyflowstep take retrpy as a runtime dependency (its rules require asking), or only as an
   optional extra?
4. For a mid-flow retry, should each attempt get fresh `Depends` objects or share the run's? And
   should a failed attempt's `output` values be discarded?
5. Is `ExceptionGroup` acceptable as an error a pyflowstep flow can raise, given the "never wrap"
   rule?
