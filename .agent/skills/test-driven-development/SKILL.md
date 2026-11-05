---
name: test-driven-development
description: >-
  Use this skill when writing tests, implementing features using TDD (Test-Driven Development),
  writing pytest suites, mocking external APIs or databases, or validating regressions.
---

# Test-Driven Development (TDD) Skill

This skill guides the implementation of software features and bug fixes through disciplined test-driven practices.

## The Red-Green-Refactor Cycle

1. **Red (Write Failing Test)**:
   - Formulate expected behavior as a concise, isolated test.
   - Run the test to confirm it fails for the expected reason (and not due to a syntax/import error).
2. **Green (Minimal Passing Implementation)**:
   - Write the simplest code that satisfies the test condition.
   - Do not prematurely optimize or add unrequested features.
   - Run the test suite and confirm all tests pass.
3. **Refactor (Clean & Optimize)**:
   - Improve code structure, readability, and modularity while keeping the test suite green.
   - Verify that test execution remains rapid and deterministic.

---

## Writing High-Quality Unit & Integration Tests

### Test Structure: AAA Pattern
Always format test functions with the Arrange-Act-Assert pattern:
```python
def test_message_forwarding_filters_empty_text():
    # Arrange
    filter_service = MessageFilter(allow_empty=False)
    raw_message = {"id": 101, "text": "   "}

    # Act
    should_forward = filter_service.evaluate(raw_message)

    # Assert
    assert should_forward is False
```

### Mocking Guidelines
- Isolate external boundaries (network calls, third-party APIs, disk writes, background threads).
- Use `unittest.mock` or `pytest-mock` (`monkeypatch`, `mocker`).
- Avoid over-mocking internal domain logic; test domain logic with real instances whenever feasible.

### Testing Edge Cases
Always include tests for:
- Empty inputs (`""`, `[]`, `{}`, `None`)
- Boundary values (0, negative numbers, maximum payload sizes)
- Timeout or network failure scenarios
- Duplicate or out-of-order events

---

## Verification Commands
Before completing any programming task, execute the project test runner:
```powershell
pytest -v
```
Ensure 100% of the relevant suite passes without unexpected skips or warnings.
