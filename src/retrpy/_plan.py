"""Plans of attempts: retry is repetition, fallback is concatenation."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial


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


def attempt[T, **P](fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs) -> Plan[T]:
    """Bind ``fn`` to its arguments as a one-attempt plan, ready for ``*`` and ``+``."""

    return Plan((Segment(partial(fn, *args, **kwargs), 1),))
