---
name: clean-code-craftsmanship
description: >-
  Use this skill when designing software architecture, writing new code modules, refactoring existing functions,
  or reviewing code quality against SOLID, Clean Code, and maintainability standards.
---

# Clean Code & Software Craftsmanship Skill

This skill guides the design, implementation, and refactoring of robust, readable, and maintainable software.

## Core Engineering Principles

### 1. SOLID Principles
- **Single Responsibility (SRP)**: Each class or function should have one reason to change. Decompose monolithic handlers into discrete processors.
- **Open/Closed (OCP)**: Extend behavior through polymorphism, composition, or strategy patterns rather than mutating established conditionals.
- **Liskov Substitution (LSP)**: Subtypes must be substitutable for their base types without altering expected behavior.
- **Interface Segregation (ISP)**: Favor small, cohesive client-specific interfaces over bloated multipurpose interfaces.
- **Dependency Inversion (DIP)**: Depend on abstractions (protocols/interfaces), not concrete implementations. Inject dependencies to facilitate testability.

### 2. Clarity & Readability Over Cleverness
- Avoid obscure one-liners or cryptic shortcuts.
- Variable and function names must reveal intent:
  - Good: `is_channel_broadcast`, `calculate_retry_backoff_seconds`
  - Bad: `flag`, `tmp`, `calc_time`
- Small, focused functions (ideally doing one conceptual task and under 30 lines).

### 3. Defensive Programming & Error Handling
- Never use bare `except:` or catch generic `Exception` without re-raising or logging with context.
- Validate inputs at the application boundary (data ingestion, API routes, user input).
- Return early (Guard Clauses) to reduce nesting depth.

### 4. Code Architecture Standards
- **Separation of Concerns**: Keep business logic separated from presentation/UI, protocol handling (e.g. Telegram client), and storage persistence.
- **Idempotency & Resilience**: Ensure functions that perform I/O operations (file writes, database updates, network calls) handle transient failures gracefully.
- **Type Safety**: Use complete type hints (`typing` module / standard types) on all function arguments and return values.

---

## Refactoring Guidelines
Before altering working code:
1. Ensure unit tests exist covering the existing behavior.
2. Refactor in small, atomic steps.
3. Keep the code runnable and passing tests at every step.
4. Eliminate duplicated code (DRY) only when duplication represents the same business responsibility, not accidental resemblance.
