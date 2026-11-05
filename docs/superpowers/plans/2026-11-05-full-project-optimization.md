# Full-Project Architecture & Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full-system architectural and performance improvements across database concurrency, forwarding throughput, batch retrieval, route garbage collection, and grounding defaults.

**Architecture:**
1. Database Layer: SQLAlchemy `Engine.connect` event hook configuring SQLite WAL mode, `busy_timeout=30000`, and `synchronous=NORMAL` for high-concurrency non-blocking database access.
2. Route Storage: Automatic deletion of temporary `review_routes:{id}` metadata upon review resolution.
3. Concurrency Layer: Replace single-lock bottleneck in `auto_forward.py` with `ProcessingLimiter` (bounded concurrency with compatible interface).
4. Telegram MTProto Batching: Batch fetch messages in chunks of 50 in `forward_range` to drastically minimize Telegram flood wait risks.
5. Grounding Safety: Disable `news_grounding_enabled` by default to avoid slow external HTTP lookups.

**Tech Stack:** Python 3.14, SQLAlchemy, Telethon, python-telegram-bot, pytest.

---

### Task 1: SQLite WAL Mode & Database Engine Resilience

**Files:**
- Modify: `app/database/database.py`
- Modify: `app/services/review_store.py`
- Test: `tests/test_repository.py`

**Steps:**
- [ ] Add event listener to SQLAlchemy `Engine` in `app/database/database.py` for SQLite connection pragma (`journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=30000`).
- [ ] Add `timeout: 30` to SQLite `connect_args` in `create_engine`.
- [ ] In `app/services/review_store.py:set_status`, delete `review_routes:{id}` from `Settings` table when status is `sent` or `rejected`.
- [ ] Run `tests/test_repository.py` and `tests/test_reviews.py` to verify database operations pass.

---

### Task 2: Multi-Channel Concurrency in Auto-Forwarding

**Files:**
- Modify: `app/telegram/auto_forward.py`
- Test: `tests/test_auto_forward.py`
- Test: `tests/test_status_logging.py`

**Steps:**
- [ ] Create `ProcessingLimiter` class in `app/telegram/auto_forward.py` supporting `.acquire()`, `.release()`, and `.locked()` with `max_concurrent=5`.
- [ ] Initialize `_processing_lock = ProcessingLimiter(max_concurrent=5)`.
- [ ] Run `tests/test_status_logging.py` and `tests/test_auto_forward.py` to confirm compatibility.

---

### Task 3: Batch Message Retrieval in Forward Service

**Files:**
- Modify: `app/telegram/forward_service.py`
- Test: `tests/test_forward_service.py`
- Test: `tests/test_transfer_regressions.py`

**Steps:**
- [ ] In `app/telegram/forward_service.py:forward_range`, pre-fetch missing messages in chunks of 50 instead of individual `client.get_messages(source, ids=[msg_id])`.
- [ ] Run `tests/test_forward_service.py` and `tests/test_transfer_regressions.py`.

---

### Task 4: Configuration & Grounding Safety

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`
- Test: Full test suite

**Steps:**
- [ ] In `app/config.py:Settings`, set `news_grounding_enabled: bool = False` by default.
- [ ] Run full test suite (`.\.venv\Scripts\python.exe -m pytest`) to ensure all tests pass.
