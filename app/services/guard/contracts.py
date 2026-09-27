import json
from dataclasses import dataclass

from app.services.ai_transport import AIRequestError


@dataclass(frozen=True)
class Verification:
    policy_pass: bool
    meaning_preserved: bool
    issues: tuple[str, ...] = ()
    repairable: bool = False

    @property
    def passed(self):
        return self.policy_pass and self.meaning_preserved and not self.issues


def validate_verification(raw):
    from app.services.output_validator import unique_fields

    try:
        if not isinstance(raw, str) or len(raw) > 6000:
            raise ValueError()
        data = json.loads(raw, object_pairs_hook=unique_fields)
        if not isinstance(data, dict) or set(data) != {
            "policy_pass",
            "meaning_preserved",
            "issues",
            "repairable",
        }:
            raise ValueError()
        if any(
            type(data[k]) is not bool for k in ("policy_pass", "meaning_preserved", "repairable")
        ):
            raise ValueError()
        issues = data["issues"]
        if (
            not isinstance(issues, list)
            or len(issues) > 8
            or any(not isinstance(x, str) or not x.strip() or len(x) > 300 for x in issues)
        ):
            raise ValueError()
        passed = data["policy_pass"] and data["meaning_preserved"]
        if passed and (issues or data["repairable"]) or not passed and not issues:
            raise ValueError()
        return Verification(
            data["policy_pass"], data["meaning_preserved"], tuple(issues), data["repairable"]
        )
    except (ValueError, KeyError, TypeError, RecursionError):
        raise AIRequestError("invalid_verification") from None
