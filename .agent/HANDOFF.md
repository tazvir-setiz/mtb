# Session Handoff Report: High-Speed AI Guard & Persian Content Policy
**Date**: 2026-11-05
**Branch / Commit**: master / 4a2cbc2

## 1. Objective
Refactor and optimize the Telegram Forwarder AI Guard system to:
1. Drastically reduce moderation latency and eliminate excessive API round-trips by streamlining the pipeline with fast-path rewrites and immediate off-topic handling.
2. Enforce the user's Persian content policy:
   - Literary check: no profanity, vulgarity, or personal insults. If useful/news content exists, rewrite cleanly; if pure abuse, drop.
   - Prohibit any insults or disrespect towards Islam, the Quran, Prophet & Ahl al-Bayt, religious rituals, the Islamic Republic, Supreme Leader (رهبری), Martyrs (شهدا), and officials.
   - Strictly prohibit any promotion, support, or whitewashing of the Pahlavi regime/monarchy and the Zionist regime (Israel) (DROP).
   - Restrict messages based on configured topics.
3. Ensure topic filtering is completely integrated with the Telegram in-app admin UI (`app/handlers/topic_settings.py`).
4. Eliminate fragile string matching and encoding failures (`quote not in original` errors on Persian Unicode/half-space).

## 2. Completed Milestones
- [x] **Refactored Guardrails System Prompt**: Wrote concise, authoritative Persian instructions in [guardrails.txt](file:///d:/Habib/py/telegram-forwarder/app/prompts/guardrails.txt) enforcing sacred boundaries, anti-propaganda (Pahlavi/Israel), politeness/rewrite rules, and single-pass JSON output.
- [x] **Resilient Persian Output Validation**: Updated [output_validator.py](file:///d:/Habib/py/telegram-forwarder/app/services/output_validator.py) with fuzzy unicode matching for Persian ZWNJ, Arabic/Persian letters, and support for the new single-pass format (`action`, `reason`, `topic`, `rewritten_text`).
- [x] **Pipeline Optimization**: Enhanced [pipeline.py](file:///d:/Habib/py/telegram-forwarder/app/services/guard/pipeline.py) to immediately return off-topic drops without redundant `drop_audit` calls, and to reuse initial rewrites seamlessly.
- [x] **Topic Filtering UI & Prompt Integration**: Linked Telegram topic configuration in [topic_settings.py](file:///d:/Habib/py/telegram-forwarder/app/handlers/topic_settings.py) and [ai_settings.py](file:///d:/Habib/py/telegram-forwarder/app/services/ai_settings.py) naturally into prompt generation.
- [x] **Comprehensive Testing**: Added [test_persian_policy_guard.py](file:///d:/Habib/py/telegram-forwarder/tests/test_persian_policy_guard.py) and ran the complete test suite.

## 3. Key Changes & File Links
- [app/prompts/guardrails.txt](file:///d:/Habib/py/telegram-forwarder/app/prompts/guardrails.txt): Complete Persian system prompt reflecting all requested rules.
- [app/services/output_validator.py](file:///d:/Habib/py/telegram-forwarder/app/services/output_validator.py): Resilient parsing and fuzzy Persian quote matching.
- [app/services/guard/pipeline.py](file:///d:/Habib/py/telegram-forwarder/app/services/guard/pipeline.py): Fast-path rewrite handling and instant off-topic drop.
- [app/services/ai_settings.py](file:///d:/Habib/py/telegram-forwarder/app/services/ai_settings.py): Clean Persian topic policy formatter.
- [tests/test_persian_policy_guard.py](file:///d:/Habib/py/telegram-forwarder/tests/test_persian_policy_guard.py): Verification tests for Persian policy and fuzzy matching.
- [docs/superpowers/plans/2026-11-05-fast-guard-and-persian-policy.md](file:///d:/Habib/py/telegram-forwarder/docs/superpowers/plans/2026-11-05-fast-guard-and-persian-policy.md): Implementation plan and architectural decision log.

## 4. Current State & Verification
- Test status: **472 passed, 0 failed** (100% green test suite in 43s).
- Verification command: `.\.venv\Scripts\python.exe -m pytest`

## 5. Known Issues / Blockers
- None. System is fully operational and verified.

## 6. Next Steps for Next Session / Agent
1. Connect live bot with valid Telegram Bot token (`BOT_TOKEN`) and run `main.py` in production.
2. In Telegram bot chat with admin, access `تنظیمات > هوش مصنوعی > فیلتر موضوعی` to customize target topics as needed.
