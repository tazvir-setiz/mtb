import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.moderation_service import moderate


def action_name(result):
    return "SEND" if result.action == "PUBLISH" else result.action


async def run(
    path: Path,
    output: Path,
    limit: int | None,
    start: int = 1,
):
    cases = json.loads(path.read_text(encoding="utf-8"))

    # --start is 1-based:
    # --start 51 means start from case number 51.
    start_index = max(start - 1, 0)
    cases = cases[start_index:]

    if limit is not None:
        cases = cases[:limit]

    results = []
    counts = Counter()

    for offset, case in enumerate(cases):
        # Real benchmark position in the original JSON file.
        case_number = start_index + offset + 1

        # Isolated chat/message ids keep benchmark cases
        # from sharing context/cache.
        chat_id = -9_000_000_000 - case_number

        result = await moderate(
            chat_id,
            case_number,
            case["text"],
        )

        actual_action = action_name(result)
        actual_label = result.label.value

        passed = (
            actual_action == case["expected_action"]
            and actual_label == case["expected_label"]
        )

        counts["passed" if passed else "failed"] += 1
        counts[f"expected_{case['expected_action']}"] += 1
        counts[f"actual_{actual_action}"] += 1

        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "text": case["text"],
                "expected_action": case["expected_action"],
                "expected_label": case["expected_label"],
                "actual_action": actual_action,
                "actual_label": actual_label,
                "actual_text": result.text,
                "reason": result.reason,
                "passed": passed,
            }
        )

        print(
            f"[{case_number:03d}] "
            f"{'PASS' if passed else 'FAIL'} "
            f"{case['id']} "
            f"expected={case['expected_action']}/{case['expected_label']} "
            f"actual={actual_action}/{actual_label}"
        )

    report = {
        "start": start,
        "total": len(cases),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "pass_rate": (
            round(counts["passed"] / len(cases), 4)
            if cases
            else 0
        ),
        "counts": dict(counts),
        "results": results,
    }

    output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nReport: {output}")
    print(
        f"Passed: {report['passed']}/{report['total']} "
        f"({report['pass_rate']:.1%})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data",
        default="tests/data/guard_benchmark_v1.json",
        help="Benchmark JSON path",
    )

    parser.add_argument(
        "--output",
        default="guard_benchmark_report.json",
        help="Output report JSON path",
    )

    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="1-based case number to start from",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of cases to run",
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            Path(args.data),
            Path(args.output),
            args.limit,
            args.start,
        )
    )