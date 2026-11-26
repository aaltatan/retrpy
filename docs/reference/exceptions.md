# Exceptions

retrpy defines no exception classes of its own. It raises standard ones:

| Raised | When |
| --- | --- |
| `ExceptionGroup("all N attempts failed", errors)` | every attempt failed with an error in `catch`; `errors` are all the failures, in order |
| the attempt's own exception, unwrapped | an attempt raised something outside `catch`; no further attempts run |
| `TypeError` | `catch` contains a class that isn't an `Exception` subclass (checked before any attempt runs) |
| `TypeError` | `plan * x` with a non-`int` `x`, or `plan + x` with a non-`Plan` `x` |
| `ValueError` | `plan * n` with `n < 1` |
| `ValueError` | calling a plan with no attempts, such as `Plan(())` |
| whatever `on_failure`, `jitter` or `sleep` raise | propagated as is; the run stops |

`BaseException`s that aren't `Exception`s (`KeyboardInterrupt`, `SystemExit`,
`asyncio.CancelledError`) are never caught, so they always propagate.

```python
import pytest

from retrpy import Plan, attempt

with pytest.raises(ValueError, match="at least 1"):
    attempt(int, "1") * -1

with pytest.raises(TypeError):
    attempt(int, "1") * 2.0

with pytest.raises(TypeError):
    attempt(int, "1") + 1

with pytest.raises(ValueError, match="empty"):
    Plan(())()
```
