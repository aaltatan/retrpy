class FakeSleep:
    """Records requested waits instead of sleeping."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class Scripted:
    """Returns or raises each outcome in turn; the last outcome repeats."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def __call__(self) -> object:
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1

        if isinstance(outcome, BaseException):
            raise outcome

        return outcome


class NetworkError(Exception):
    pass
