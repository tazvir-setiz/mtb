# MTB — separated classifier / writer architecture

This patch replaces the old "classifier that sometimes also writes" design with:

1. ANALYZE / REASSESS — classification only; `REWRITE` means "writer needed".
2. GENERATE_REWRITE — dedicated writer contract, no moderation labels.
3. VERIFY — independent policy + meaning check.
4. REPAIR_REWRITE — writer is called again with verifier issues.
5. DROP for abuse still requires analyze + independent drop audit. The writer never authorizes DROP.

Changed files:
- app/services/guard/contracts.py
- app/services/ai_response.py
- app/services/output_validator.py
- app/services/ai_service.py
- app/services/guard/pipeline.py
- app/prompts/guardrails.txt
- app/services/rule_guard.py

Added regression tests:
- tests/test_rewrite_architecture_v3.py

Important behavior:
- `REWRITE` classification responses must have `text=null`.
- Writer output is:
  {"success": true, "text": "...", "preserved_meaning": "...", "reason": null}
  or a failure object with success=false.
- Writer cannot return ABUSE/OK/POLITICAL/etc.
- Meaning verification explicitly checks semantic roles, polarity, subject/object and question/request structure.
- Locally detected pure abuse is narrower, so meaningful vulgar sentences reach the AI pipeline.

After replacing the files, run:
    pytest tests/test_rewrite_architecture_v3.py
Then run:
    pytest

Note: some older tests in the repository mock `ai_service.classify(..., rewrite=True)`.
Those tests describe the old architecture and should be migrated to mock
`ai_service.generate_rewrite` instead. The new regression file demonstrates the new pattern.
