# MTB Guard V4.1

This patch introduces the multi-stage guard architecture:

1. Analyze
2. Reassess only if ambiguous
3. Independent drop audit
4. Meaning decomposition
5. Rewrite generation
6. Policy judge
7. Meaning judge
8. Repair writer if needed
9. Final policy judge
10. Final meaning judge
11. SEND / DROP / REVIEW

Important changes:
- New labels: HATE, THREAT
- Classification no longer writes replacement text.
- Meaning decomposition separates protected meaning from removable abusive content.
- Policy and meaning verification are separate AI calls.
- One repair pass is allowed and is judged again by both judges.
- Pure ABUSE gets a final meaning-decomposition salvage check.
- Existing guard profile schema is NOT migrated; HATE and THREAT stay always enabled.
- Defaults: 1800 output tokens, 12 stages, 12 requests, 150 seconds total budget.

## After copying files

Run:
    pytest tests/test_guard_v4_contracts.py -q
    pytest tests/test_guard_benchmark_schema.py -q

Then smoke-test 10 real AI cases:
    python scripts/run_guard_benchmark.py --limit 10

If that works, run all 150:
    python scripts/run_guard_benchmark.py

The live benchmark writes:
    guard_benchmark_report.json

Do not treat the first 150-case score as final. Review failures by category, tune prompts,
then rerun the same fixed corpus. This is the point of the regression benchmark.
