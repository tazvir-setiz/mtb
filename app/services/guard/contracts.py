from dataclasses import dataclass

from app.services.ai_transport import AIRequestError


@dataclass(frozen=True)
class MeaningDecomposition:
    protected_meaning: tuple[str, ...]
    removable_meaning: tuple[str, ...]
    entities_relations: tuple[str, ...]
    ambiguities: tuple[str, ...] = ()

    @property
    def has_protected_meaning(self) -> bool:
        return bool(self.protected_meaning)


@dataclass(frozen=True)
class RewriteDraft:
    success: bool
    text: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class PolicyVerdict:
    passed: bool
    issues: tuple[str, ...] = ()
    repairable: bool = False


@dataclass(frozen=True)
class MeaningVerdict:
    passed: bool
    issues: tuple[str, ...] = ()
    repairable: bool = False


def _response(raw, maximum=12000):
    from app.services.response_format import response_object
    return response_object(raw, maximum)


def _strings(value, *, maximum=12, item_max=500):
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not isinstance(x, str) or not x.strip() or len(x) > item_max for x in value)
    ):
        raise ValueError()
    return tuple(x.strip() for x in value)


def validate_meaning(raw):
    try:
        data = _response(raw)
        if set(data) != {
            "protected_meaning",
            "removable_meaning",
            "entities_relations",
            "ambiguities",
        }:
            raise ValueError()
        return MeaningDecomposition(
            _strings(data["protected_meaning"]),
            _strings(data["removable_meaning"]),
            _strings(data["entities_relations"]),
            _strings(data["ambiguities"]),
        )
    except Exception as exc:
        if isinstance(exc, AIRequestError):
            raise
        raise AIRequestError("invalid_meaning", detail="meaning_schema") from None


def validate_rewrite_draft(raw, max_chars):
    try:
        data = _response(raw, max_chars * 2 + 3000)
        if set(data) != {"success", "text", "reason"} or type(data["success"]) is not bool:
            raise ValueError()
        if data["success"]:
            if (
                not isinstance(data["text"], str)
                or not data["text"].strip()
                or len(data["text"]) > max_chars
                or data["reason"] is not None
            ):
                raise ValueError()
        else:
            if data["text"] is not None or not isinstance(data["reason"], str) or not data["reason"].strip():
                raise ValueError()
        return RewriteDraft(data["success"], data["text"], data["reason"])
    except Exception as exc:
        if isinstance(exc, AIRequestError):
            raise
        raise AIRequestError("invalid_rewrite", detail="rewrite_schema") from None


def _validate_judge(raw, cls, reason):
    try:
        data = _response(raw, 6000)
        required = {"passed", "issues"}
        allowed = required | {"repairable"}
        if not required.issubset(data) or set(data) - allowed:
            raise ValueError()
        if type(data["passed"]) is not bool:
            raise ValueError()
        issues = _strings(data["issues"], maximum=8, item_max=300)
        repairable = data.get("repairable", bool(not data["passed"] and issues))
        if type(repairable) is not bool:
            raise ValueError()
        if data["passed"] and issues:
            raise ValueError()
        if not data["passed"] and not issues:
            raise ValueError()
        if data["passed"]:
            repairable = False
        return cls(data["passed"], issues, repairable)
    except Exception as exc:
        if isinstance(exc, AIRequestError):
            raise
        raise AIRequestError(reason, detail="judge_schema") from None


def validate_policy_verdict(raw):
    return _validate_judge(raw, PolicyVerdict, "invalid_policy_verdict")


def validate_meaning_verdict(raw):
    return _validate_judge(raw, MeaningVerdict, "invalid_meaning_verdict")
