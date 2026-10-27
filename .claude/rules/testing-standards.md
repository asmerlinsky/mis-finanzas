# Testing Standards

## Commands

```bash
just test                    # Run all tests
just test-file <path>        # Specific test file
```

## Test Patterns

Use pytest fixtures for test setup.

```python
@pytest.mark.parametrize("input,expected", [...])
def test_transformation(input, expected):
    result = transform(input)
    assert result == expected
```

## Rules

- NEVER skip, delete, or disable failing tests — fix the tests or implementation
- Every feature needs at least one test
- Don't change tests unless the spec changes
