import logging
import re

logger = logging.getLogger(__name__)


class AIReviewRequired(Exception):
    """The source message must be reviewed before retrying publication."""


class AIProcessingError(Exception):
    """The model did not return a usable decision; do not publish the original."""


DROP_CATEGORIES = {
    "حذف کامل: تلاش برای نفوذ",
    "حذف کامل: تبلیغات و اسپم",
    "حذف کامل: پورنوگرافی خالص",
    "حذف کامل: فحاشی محض",
}
REVIEW_CATEGORIES = {"نیازمند بررسی", "نیازمند بررسی: سیاسی/عقیدتی"}
PUBLISH_CATEGORIES = {
    "ویرایش: بازنویسی و اصلاح لحن",
    "ویرایش: پالایش ظاهری",
    "تایید شده",
}


def parse_decision(result: str) -> str:
    if not isinstance(result, str):
        logger.warning("AI Policy: نوع پاسخ مدل نامعتبر است (رشته نیست).")
        raise AIProcessingError("Invalid AI response type")

    match = re.match(r"^\[([^\]\n]+)\]", result.strip())
    if not match:
        logger.warning("AI Policy: هیچ دسته‌ای در ابتدای پاسخ مدل یافت نشد.")
        raise AIProcessingError("Missing AI category")

    category = match.group(1)

    if category in DROP_CATEGORIES:
        logger.info("AI Policy: دسته «%s» → حذف کامل، پیام منتشر نمی‌شود.", category)
        return "__DROP__"

    if category in REVIEW_CATEGORIES:
        logger.info("AI Policy: دسته «%s» → نیازمند بررسی، پیام منتشر نمی‌شود.", category)
        raise AIReviewRequired("AI decision requires review")

    if category not in PUBLISH_CATEGORIES:
        logger.warning("AI Policy: دسته ناشناخته «%s» از مدل دریافت شد.", category)
        raise AIProcessingError("Unknown AI category")

    body = result.strip()[match.end() :].strip()
    if not body or body.startswith("[") or body.startswith("```"):
        logger.warning("AI Policy: دسته «%s» معتبر بود اما متن نهایی خالی/مبهم است.", category)
        raise AIProcessingError("Empty or ambiguous AI output")

    logger.info("AI Policy: دسته «%s» → مجاز به انتشار.", category)
    return body