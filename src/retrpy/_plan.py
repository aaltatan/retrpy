"""Plans of attempts: retry is repetition, fallback is concatenation."""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from functools import partial
from typing import Self, cast


@dataclass(frozen=True, slots=True)
class Segment[T]:
    """One zero-argument callable repeated ``count`` times; backoff restarts per segment."""

    fn: Callable[[], T]
    count: int


@dataclass(frozen=True, slots=True)
class Plan[T]:
    """An immutable, ordered sequence of attempts; the first one that succeeds wins.

    The plan keeps its segments rather than a flat list of calls, because the wait between
    attempts grows within a segment and restarts when the plan falls back to the next one.
    """

    segments: tuple[Segment[T], ...]

    def __len__(self) -> int:
        return sum(segment.count for segment in self.segments)

    def __iter__(self) -> Iterator[Callable[[], T]]:
        for segment in self.segments:
            yield from [segment.fn] * segment.count

    def __call__(
        self,
        *,
        delay: float = 0.0,
        backoff: float = 1.0,
        catch: tuple[type[Exception], ...] = (Exception,),
        max_delay: float | None = None,
        jitter: Callable[[float], float] | None = None,
        on_failure: Callable[[Exception, int], None] | None = None,
        sleep: Callable[[float], object] = time.sleep,
    ) -> T:
        """Run the attempts in order and return the first success.

        Exceptions outside ``catch`` propagate at once, unwrapped. Within a segment the wait
        before the next try is ``delay * backoff**k``, with ``k`` restarting at each segment,
        so a backup source never inherits the primary's grown delay. Switching segments does
        not wait. ``jitter`` maps each wait to a new one (it owns its RNG, so tests can pass a
        deterministic one), and ``max_delay`` then caps it; a wait of zero or less skips
        ``sleep``. ``on_failure(error, number)`` sees every caught failure, numbered from 1
        across the whole plan, including the last. When every attempt fails, an
        ``ExceptionGroup`` holds all the failures in order, so callers can use ``except*``.
        """

        if not self.segments:
            msg = "Cannot run an empty plan"
            raise ValueError(msg)

        errors: list[Exception] = []

        for segment in self.segments:
            for k in range(segment.count):
                try:
                    return segment.fn()

                except catch as error:
                    errors.append(error)

                    if on_failure is not None:
                        on_failure(error, len(errors))

                if (
                    k < segment.count - 1
                    and (wait := _wait(delay, backoff, k, jitter, max_delay)) > 0
                ):
                    sleep(wait)

        msg = f"all {len(errors)} attempts failed"

        raise ExceptionGroup(msg, errors)

    def __mul__(self, n: int) -> Self:
        if not isinstance(n, int):
            return NotImplemented

        if n < 1:
            msg = f"Plan can only be repeated at least 1 time, got {n}"
            raise ValueError(msg)

        # One segment grows its count so its backoff keeps growing; anything else repeats.
        if len(self.segments) == 1:
            (segment,) = self.segments

            return replace(self, segments=(Segment(segment.fn, segment.count * n),))

        return replace(self, segments=self.segments * n)

    __rmul__ = __mul__

    def __add__[U](self, other: "Plan[U]") -> "Plan[T | U]":
        if not isinstance(other, Plan):
            return NotImplemented

        segments: tuple[Segment[T | U], ...] = (*self.segments, *other.segments)

        # Widen self's type so replace() keeps the subclass and accepts the wider segments.
        return replace(cast("Plan[T | U]", self), segments=segments)


def attempt[T, **P](fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Plan[T]:
    """Bind ``fn`` to its arguments as a one-attempt plan, ready for ``*`` and ``+``."""
    return Plan((Segment(partial(fn, *args, **kwargs), 1),))


# --- private helpers


def _wait(
    delay: float,
    backoff: float,
    k: int,
    jitter: Callable[[float], float] | None,
    max_delay: float | None,
) -> float:
    wait = delay * backoff**k

    if jitter is not None:
        wait = jitter(wait)

    if max_delay is not None:
        wait = min(wait, max_delay)

    return wait
