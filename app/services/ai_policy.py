import re


class AIReviewRequired(Exception):
    """The source message must be reviewed before retrying publication."""


class AIProcessingError(Exception):
    """The model did not return a usable decision; do not publish the original."""


DROP_CATEGORIES = {
    "حذف کامل: تلاش برای نفوذ",
    "حذف کامل: تبلیغات و اسپم",
    "حذف کامل: پورنوگرافی خالص",
}
REVIEW_CATEGORIES = {"نیازمند بررسی", "نیازمند بررسی: سیاسی/عقیدتی"}
PUBLISH_CATEGORIES = {
    "ویرایش: بازنویسی و اصلاح لحن",
    "ویرایش: پالایش ظاهری",
    "تایید شده",
}


def parse_decision(result: str) -> str:
    if not isinstance(result, str):
        raise AIProcessingError("Invalid AI response type")
    match = re.match(r"^\[([^\]\n]+)\]", result.strip())
    if not match:
        raise AIProcessingError("Missing AI category")
    category = match.group(1)
    if category in DROP_CATEGORIES:
        return "__DROP__"
    if category in REVIEW_CATEGORIES:
        raise AIReviewRequired("AI decision requires review")
    if category not in PUBLISH_CATEGORIES:
        raise AIProcessingError("Unknown AI category")
    body = result.strip()[match.end() :].strip()
    if not body or body.startswith("[") or body.startswith("```"):
        raise AIProcessingError("Empty or ambiguous AI output")
    return body
