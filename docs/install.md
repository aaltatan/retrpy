# Installation

retrpy needs **Python 3.12 or newer** and has **no dependencies**.

=== "uv"

    ```bash
    uv add retrpy
    ```

=== "pip"

    ```bash
    pip install retrpy
    ```

The package ships a `py.typed` marker and is `mypy --strict` clean, so type checkers see the
result type of every plan.

## Check it works

```python
from retrpy import attempt

plan = attempt(int, "41") + attempt(lambda: 0)

assert plan() == 41
assert len(plan) == 2
```
