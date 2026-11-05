# Fast AI Guard & Persian Content Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Telegram Forwarder AI Guard into a high-speed, single-pass pipeline that enforces the user's Persian content rules, provides in-app Telegram topic filtering, rewrites mixed messages cleanly, and eliminates latency and validation errors.

**Architecture:** 
1. Single-Pass Fast Path: A unified LLM call replaces the 8-stage cascade, returning structured verdict (`action`, `label`, `reason`, `topic`, `rewritten_text`).
2. Native Persian Guardrails: Clear, authoritative system instructions matching the user's policy (politeness, sacred boundaries, anti-propaganda, news preservation, topic adherence).
3. Resilient Parsing: Fuzzy Unicode matching and robust JSON extraction to prevent crashes from Persian typography or minor schema deviations.
4. Telegram UI Integration: Seamless topic management in `topic_settings.py` syncing to the prompt.

**Tech Stack:** Python 3.14, python-telegram-bot, Telethon, SQLAlchemy, httpx, pytest.

**Spec:** User requirements from chat:
- Politeness and literary check: No profanity, vulgarity, or personal insults.
- Sacred boundaries: No insults towards Islam, the Quran, Prophet & Ahl al-Bayt, religious rituals, Islamic Republic, Supreme Leader, Martyrs, or officials.
- Red lines: Strictly prohibit support/promotion of the Pahlavi regime/monarchy and Zionist regime (Israel) (DROP).
- Rewrite policy: If a message has inappropriate wording but contains substantive news/useful info, rewrite it cleanly to preserve the core message.
- Topic restriction: Configurable from inside Telegram.

## Global Constraints
- Total processing time per message must be < 3 seconds (single LLM round-trip).
- All Persian typography (half-spaces, Arabic/Persian Kaf and Yeh) must be handled transparently without throwing format errors.
- Preserve backward compatibility with existing Telegram bot handlers and database schema.

## Review Focus
1. Persian Unicode mismatch in quotes: Ensure normalized comparison so `می شود` vs `می‌شود` or `ی/ي` never triggers `ValueError`.
2. Off-topic handling: Confirm messages outside configured topics are properly dropped or sent to review based on the Telegram setting.
3. Rewrite fidelity: Ensure rewritten text completely removes insults while faithfully preserving the substantive factual/news proposition.
4. Pure violation handling: Ensure pure abuse or pure propaganda is immediately dropped without attempting an empty rewrite.
5. In-app Telegram topic updates: Ensure changing topics in Telegram immediately reflects in subsequent moderation decisions.

---

### Task 1: Refactor Guardrails System Prompt to Persian

**Files:**
- Modify: `app/prompts/guardrails.txt`
- Modify: `app/services/ai_settings.py`
- Test: `tests/test_ai_policy.py`

**Steps:**
- [ ] Write the complete, unified Persian system prompt in `app/prompts/guardrails.txt` covering:
  - Role and authority
  - Literary tone & profanity check
  - Sacred Islamic boundaries (Islam, Quran, Prophet, Ahl al-Bayt, rituals)
  - Islamic Republic, Leader, Martyrs, officials respect
  - Prohibition of Pahlavi/monarchy & Israeli promotion
  - Intelligent rewriting instruction (useful news kept, bad words cleaned)
  - Single-pass JSON response schema
- [ ] Update `format_topic_policy` in `app/services/ai_settings.py` to output natural Persian instructions for topic restriction.
- [ ] Run existing prompt tests to verify formatting.

---

### Task 2: Resilient Output Validation & Parsing for Persian Text

**Files:**
- Modify: `app/services/output_validator.py`
- Modify: `app/services/ai_response.py`
- Test: `tests/test_validators.py`

**Steps:**
- [ ] Update `output_validator.py` to support the unified fast response format (`action`, `label`, `reason`, `topic`, `rewritten_text`).
- [ ] Add Persian Unicode normalization to evidence/quote matching so ZWNJ (`\u200c`) and character variations never throw `ValueError`.
- [ ] Enhance `ai_response.py` to extract JSON reliably even if models enclose in markdown code fences or prepend brief text.
- [ ] Add unit tests in `tests/test_validators.py` verifying fuzzy Persian matching and JSON parsing resilience.

---

### Task 3: Unified Single-Pass Evaluation & Rewriting in AI Service & Pipeline

**Files:**
- Modify: `app/services/ai_service.py`
- Modify: `app/services/guard/pipeline.py`
- Modify: `app/services/moderation_service.py`
- Test: `tests/test_guard_pipeline.py`

**Steps:**
- [ ] Implement `evaluate_single_pass` in `app/services/ai_service.py` that sends the message to the model and receives the complete verdict and optional rewrite in ONE request.
- [ ] Update `GuardPipeline.decide()` in `app/services/guard/pipeline.py` to use `evaluate_single_pass` as the primary fast path.
- [ ] Ensure `moderation_service.py` passes target topics and settings cleanly into the pipeline.
- [ ] Verify that mixed messages return `Label.REWRITE` with the cleaned text, and clean messages return `Label.OK` or `Label.SANITIZE`.

---

### Task 4: In-App Telegram Topic Filtering Verification & End-to-End Testing

**Files:**
- Modify: `app/handlers/topic_settings.py` (if any UI refinement needed)
- Test: `tests/test_topic_settings.py`
- Test: `tests/test_guard_persian_slang_regression.py`

**Steps:**
- [ ] Review `topic_settings.py` and ensure the menu display, toggle, edit, and clear flows work seamlessly.
- [ ] Add test cases in `tests/test_topic_settings.py` verifying that enabling topic filter restricts off-topic messages according to the configured action (`DROP` or `REVIEW`).
- [ ] Run test suite (`.\.venv\Scripts\python.exe -m pytest`) to ensure all tests pass.
