from app.services.review_kind import (
    ReviewKind,
    encode_guard_block,
    is_guard_block,
    parse_review_reason,
)


def test_guard_block_encoding_preserves_label_and_reason():
    encoded = encode_guard_block("ABUSE", "policy_violation")
    assert encoded == "guard_block:ABUSE:policy_violation"

    parsed = parse_review_reason(encoded)
    assert parsed.kind is ReviewKind.GUARD_BLOCK
    assert parsed.guard_label == "ABUSE"
    assert parsed.reason == "policy_violation"


def test_guard_block_parser_supports_legacy_rows():
    parsed = parse_review_reason("guard_block:abuse")
    assert parsed.kind is ReviewKind.GUARD_BLOCK
    assert parsed.guard_label == "ABUSE"
    assert parsed.reason == "abuse"
    assert is_guard_block("guard_block:abuse")


def test_normal_review_reason_remains_unchanged():
    parsed = parse_review_reason("low_confidence")
    assert parsed.kind is ReviewKind.NORMAL
    assert parsed.guard_label is None
    assert parsed.reason == "low_confidence"
    assert not is_guard_block("low_confidence")


def test_preserve_review_kind_keeps_guard_block_identity():
    from app.services.review_kind import preserve_review_kind

    assert (
        preserve_review_kind("guard_block:ABUSE:original_reason", "ai_draft")
        == "guard_block:ABUSE:original_reason"
    )
    assert preserve_review_kind("low_confidence", "timeout") == "timeout"
