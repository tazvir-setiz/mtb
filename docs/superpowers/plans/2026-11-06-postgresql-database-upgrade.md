# PostgreSQL Enterprise Database Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate first-class PostgreSQL support alongside optimized SQLite (dual-engine architecture) with connection pooling, cloud URL normalization, and Docker Compose orchestration.

**Architecture:**
1. Dual-Engine SQLAlchemy Configuration: In `app/database/database.py`, automatically detect database type from `DATABASE_URL`. If PostgreSQL, configure `pool_pre_ping=True`, `pool_size=10`, `max_overflow=20`, `pool_recycle=300`. If SQLite, configure WAL mode and `timeout=30`.
2. Cloud Compatibility: Automatically normalize `postgres://` URLs (standard on Railway/Heroku/Render) to `postgresql+psycopg://`.
3. Dependency Management: Add `psycopg[binary]>=3.2` to `requirements.txt`.
4. Orchestration: Provide `docker-compose.yml` with PostgreSQL 16 Alpine service, healthcheck, and persistent volume.

**Tech Stack:** Python 3.14, SQLAlchemy 2.0, Psycopg 3 (psycopg[binary]), PostgreSQL 16, Docker Compose.

---

### Task 1: Dependencies and URL Normalization

**Files:**
- Modify: `requirements.txt`
- Modify: `app/database/database.py`
- Test: `tests/test_database_backends.py`

**Steps:**
- [ ] Add `psycopg[binary]>=3.2` to `requirements.txt`.
- [ ] Implement `normalize_database_url(url: str) -> str` in `app/database/database.py`.
- [ ] Configure PostgreSQL connection pool options when dialect is PostgreSQL.
- [ ] Create `tests/test_database_backends.py` to test URL normalization and engine configuration.

---

### Task 2: Containerization & Documentation

**Files:**
- Create: `docker-compose.yml`
- Modify: `.env.example`
- Test: Full test suite

**Steps:**
- [ ] Create `docker-compose.yml` defining the `postgres` and `bot` services.
- [ ] Update `.env.example` with PostgreSQL connection examples.
- [ ] Run full test suite (`.\.venv\Scripts\python.exe -m pytest`) to ensure all tests pass.
