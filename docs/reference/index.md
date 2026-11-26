# Reference

- [API](api.md): `attempt` and `Plan`, every operator and run parameter.
- [Exceptions](exceptions.md): what is raised, and when.

Everything is importable from the package root:

```python
import retrpy

assert sorted(retrpy.__all__) == ["Plan", "attempt"]
```
