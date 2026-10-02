from dataclasses import dataclass
from enum import Enum


GUARD_BLOCK_PREFIX = "guard_block:"


class ReviewKind(str, Enum):
    NORMAL = "normal"
    GUARD_BLOCK = "guard_block"


@dataclass(frozen=True)
class ReviewReason:
    kind: ReviewKind
    reason: str
    guard_label: str | None = None


def encode_guard_block(label: str, reason: str = "") -> str:
    normalized_label = (label or "UNKNOWN").strip().upper()
    normalized_reason = (reason or "").strip()
    value = f"{GUARD_BLOCK_PREFIX}{normalized_label}"
    if normalized_reason and normalized_reason.lower() != normalized_label.lower():
        value += f":{normalized_reason}"
    return value[:100]


def parse_review_reason(value: str | None) -> ReviewReason:
    raw = (value or "").strip()
    if not raw.startswith(GUARD_BLOCK_PREFIX):
        return ReviewReason(ReviewKind.NORMAL, raw)

    payload = raw[len(GUARD_BLOCK_PREFIX):]
    label, separator, reason = payload.partition(":")
    normalized_label = (label or "UNKNOWN").strip().upper()
    return ReviewReason(
        ReviewKind.GUARD_BLOCK,
        reason.strip() if separator else normalized_label.lower(),
        normalized_label,
    )


def is_guard_block(value: str | None) -> bool:
    return parse_review_reason(value).kind is ReviewKind.GUARD_BLOCK


def preserve_review_kind(existing: str | None, reason: str) -> str:
    parsed = parse_review_reason(existing)
    if parsed.kind is ReviewKind.GUARD_BLOCK:
        # Keep the original DROP label and detailed reason; draft/retry state lives elsewhere.
        return existing or encode_guard_block("UNKNOWN")
    return reason
