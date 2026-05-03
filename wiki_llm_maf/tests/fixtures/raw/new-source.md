# New Source: Python Type Hints

Python type hints allow developers to annotate expected types in function signatures and variable declarations.

## Key Points

- Type hints are optional and don't affect runtime behavior.
- Tools like `mypy` use them for static analysis.
- `typing` module provides complex types: `List`, `Dict`, `Optional`, `Union`.
- Python 3.10+ supports `X | Y` union syntax.

## Example

```python
def greet(name: str, times: int = 1) -> str:
    return (f"Hello, {name}!\n") * times
```
