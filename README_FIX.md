# Fix: auto rewrite falling into REVIEW

Main causes seen in your logs:
- verifier was receiving conflicting output instructions from the classifier policy
- first verifier output often failed schema validation
- `repairable=false` caused immediate REVIEW without a second rewrite attempt
- even already-OK messages were being semantically re-verified against themselves

This patch:
1. isolates verifier prompt/output contract
2. allows removal of abusive wording without treating that alone as meaning loss
3. forces one repair attempt for generated rewrites before REVIEW
4. accepts missing `repairable` on failed verifier responses and defaults it to true
5. skips redundant semantic verification for messages already classified as publishable

Replace:
- app/services/guard/contracts.py
- app/services/ai_service.py
- app/services/guard/pipeline.py
