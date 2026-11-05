---
name: task-handoff
description: >-
  Use this skill when preparing to end a session, handing off work to another agent or session,
  generating a task handoff report, creating structured state checkpoints, or resuming an ongoing task.
---

# Task Handoff & Session Transition Skill

This skill provides a systematic protocol for transferring state, context, code changes, and pending tasks between agent sessions or subagents with zero information loss.

## When to Trigger
- The current conversation context is getting large or needs to be resumed in a fresh session.
- Delegating tasks or switching roles between autonomous subagents.
- Completing a chunk of work that requires human review before proceeding to the next phase.
- User asks to "handoff", "summarize state", "save checkpoint", or "prepare transfer".

---

## The 5-Point Handoff Protocol

When generating a handoff artifact or updating handoff documentation:

### 1. Goal & Context Summary
- **Original Objective**: Exact problem statement or feature requested by the user.
- **Scope & Constraints**: Environment variables, operational limits, tools/frameworks in use.
- **Current Status**: Completed milestones vs. in-progress vs. blocked.

### 2. File & State Delta
- **Files Modified**: Explicit file paths with line-range summaries or git diff overview.
- **Files Created**: New modules, configuration files, test scripts, or documentation.
- **State Changes**: Migrations executed, dependencies installed, running background processes or services.

### 3. Decisions & Trade-offs Made
- **Architectural Decisions**: Why specific libraries, patterns, or data structures were chosen.
- **Discarded Approaches**: Approaches attempted that failed or were rejected (to prevent the next agent from repeating mistakes).

### 4. Verification & Health Check
- **Tests Executed**: Exact test commands run and their pass/fail outcomes.
- **Outstanding Warnings/Errors**: Any known linting warnings, unhandled edge cases, or pending test failures.
- **Reproduction Steps**: Exact shell commands to start the application, run unit tests, or verify current state.

### 5. Actionable Next Steps (Immediate Backlog)
- Ordered, numbered list of exact atomic actions the next agent must execute.
- Do not use vague items like "improve performance"; use specific items like:
  1. Add unit test for empty payload in `app/handlers/message.py`.
  2. Implement exponential backoff in `telegram_client.py:reconnect()`.

---

## Standard Handoff Artifact Template

Save or output the handoff using this structure (e.g., in `.agent/HANDOFF.md` or as an artifact):

```markdown
# Session Handoff Report: [Feature/Task Name]
**Date**: [ISO Timestamp]
**Branch / Commit**: [Git branch or HEAD commit hash]

## 1. Objective
[Concise summary of user request and target outcome]

## 2. Completed Milestones
- [x] [Step 1 accomplished with details]
- [x] [Step 2 accomplished with details]

## 3. Key Changes & File Links
- [file_path](file:///absolute/path): [Explanation of changes made]

## 4. Current State & Verification
- Test status: [e.g. 14 passed, 0 failed]
- Verification command: `pytest tests/test_feature.py`

## 5. Known Issues / Blockers
- [Issue description or "None"]

## 6. Next Steps for Next Session / Agent
1. [First immediate priority]
2. [Second priority]
```

---

## Resuming from a Handoff

When receiving or starting from an existing handoff:
1. Locate and inspect the handoff file (e.g., `.agent/HANDOFF.md` or latest checkpoint).
2. Run the verification commands specified in the report to confirm the baseline state.
3. Validate that git status matches the reported file delta.
4. Begin execution directly with step 1 of the "Next Steps" backlog without redundant re-analysis.
