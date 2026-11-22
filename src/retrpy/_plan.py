"""Plans of attempts: retry is repetition, fallback is concatenation."""

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
