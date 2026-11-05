---
name: systematic-debugging
description: >-
  Use this skill when diagnosing bugs, investigating runtime exceptions, fixing broken tests,
  troubleshooting unexpected behaviors, or performing root-cause analysis in code.
---

# Systematic Debugging Skill

This skill enforces a rigorous, evidence-based debugging procedure. It replaces trial-and-error guesswork with systematic root-cause isolation and regression-safe remedies.

## Core Rules of Systematic Debugging
1. **Never guess**: Do not edit code randomly hoping the error disappears.
2. **Reproduce first**: Always produce a minimal, consistent reproduction script or failing unit test before modifying application code.
3. **Isolate root cause**: Distinguish between the symptom (e.g. `AttributeError`, `IndexError`) and the underlying flaw (e.g. unhandled async race condition, improper state initialization).
4. **Minimal diff**: Apply the surgical fix addressing the root cause without introducing extraneous changes.
5. **Verify against regression**: Run all tests in the module to ensure no existing functionality was broken.

---

## 4-Stage Diagnostic Workflow

### Phase 1: Evidence Gathering & Reproduction
- Capture the full traceback, error message, and environment context.
- Identify the exact line number, function, and caller sequence.
- Write a failing test or isolated scratch script (in the conversation scratchpad) that triggers the failure deterministically.

### Phase 2: Root-Cause Analysis (RCA)
- Trace the lifecycle of inputs and variable state leading up to the failure point.
- Check assumptions:
  - Is an optional value `None`?
  - Did an asynchronous operation resolve out of expected order?
  - Are type annotations matching actual runtime types?
  - Has an external API payload schema changed?
- State the explicit hypothesis:
  > *"The failure happens because `payload['sender']` is undefined when incoming messages originate from a channel rather than a user."*

### Phase 3: Surgical Correction
- Design a fix that directly resolves the root cause while maintaining architectural consistency.
- Add defensive checks and proper error recovery if the condition can occur in normal operation.
- Keep the diff focused and clean. Avoid incidental refactoring in the middle of a bug fix.

### Phase 4: Verification & Regression Testing
- Re-run the reproduction test: Verify that it now passes (`Green`).
- Run the full suite of relevant tests:
  ```powershell
  pytest tests/ -v
  ```
- Verify that error handling does not silently swallow exceptions or hide secondary failures.

---

## Diagnostic Checklist
- [ ] Has the error been reproduced deterministically?
- [ ] Is the root cause clearly identified (not just the symptom)?
- [ ] Was the fix verified with a passing test?
- [ ] Were existing tests re-run to guarantee no regression?
- [ ] Are logs/metrics added if this failure mode could reoccur silently in production?
