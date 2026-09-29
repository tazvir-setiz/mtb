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


@dataclass(frozen=True)
class RewriteDraft:
    success: bool
    text: str | None = None
    preserved_meaning: str | None = None
    reason: str | None = None


def validate_verification(raw):
    from app.services.response_format import OutputFormatError, response_object

    try:
        data = response_object(raw, 6000)
        required = {"policy_pass", "meaning_preserved", "issues"}
        allowed = required | {"repairable"}

        if not isinstance(data, dict) or not required.issubset(data) or set(data) - allowed:
            raise ValueError()

        if any(type(data[k]) is not bool for k in ("policy_pass", "meaning_preserved")):
            raise ValueError()

        issues = data["issues"]
        if (
            not isinstance(issues, list)
            or len(issues) > 8
            or any(not isinstance(x, str) or not x.strip() or len(x) > 300 for x in issues)
        ):
            raise ValueError()

        passed = data["policy_pass"] and data["meaning_preserved"]

        if "repairable" in data:
            if type(data["repairable"]) is not bool:
                raise ValueError()
            repairable = data["repairable"]
        else:
            repairable = bool(not passed and issues)

        if passed:
            if issues:
                raise ValueError()
            repairable = False
        elif not issues:
            raise ValueError()

        return Verification(
            data["policy_pass"],
            data["meaning_preserved"],
            tuple(issues),
            repairable,
        )
    except OutputFormatError as exc:
        raise AIRequestError("invalid_verification", detail=exc.detail) from None
    except (ValueError, KeyError, TypeError, RecursionError):
        raise AIRequestError("invalid_verification", detail="verification_schema") from None


def validate_rewrite_draft(raw, max_chars: int):
    from app.services.response_format import OutputFormatError, response_object

    try:
        data = response_object(raw, max_chars * 2 + 3000)
        if not isinstance(data, dict) or set(data) != {
            "success",
            "text",
            "preserved_meaning",
            "reason",
        }:
            raise ValueError()

        success = data["success"]
        text = data["text"]
        preserved = data["preserved_meaning"]
        reason = data["reason"]

        if type(success) is not bool:
            raise ValueError()

        if success:
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > max_chars
                or "```" in text
            ):
                raise ValueError()
            if (
                not isinstance(preserved, str)
                or not preserved.strip()
                or len(preserved) > 600
            ):
                raise ValueError()
            if reason is not None:
                raise ValueError()
        else:
            if text is not None or preserved is not None:
                raise ValueError()
            if (
                not isinstance(reason, str)
                or not reason.strip()
                or len(reason) > 300
            ):
                raise ValueError()

        return RewriteDraft(success, text, preserved, reason)
    except OutputFormatError as exc:
        raise AIRequestError("invalid_rewrite", detail=exc.detail) from None
    except (ValueError, KeyError, TypeError, RecursionError):
        raise AIRequestError("invalid_rewrite", detail="rewrite_schema") from None
