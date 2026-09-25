from __future__ import annotations

MAX_RANGE_SIZE = 5000


def is_admin_user(user_id: int, admin_ids: list[int]) -> bool:
    return user_id in admin_ids


def validate_channel_input(raw: str) -> str | None:
    raw = raw.strip()
    if not raw:
        return "ورودی خالی است."
    if len(raw) > 100:
        return "ورودی بیش از حد طولانی است."
    return None


def validate_message_id(raw: str) -> tuple[int | None, str | None]:
    raw = raw.strip()
    if not raw.isdigit():
        return None, "Message ID باید یک عدد صحیح مثبت باشد."
    value = int(raw)
    if value <= 0:
        return None, "Message ID باید بزرگ‌تر از صفر باشد."
    return value, None


def validate_range(start_id: int, end_id: int) -> str | None:
    if end_id < start_id:
        return "Message ID پایان باید بزرگ‌تر یا مساوی شروع باشد."
    if end_id - start_id + 1 > MAX_RANGE_SIZE:
        return f"بازه انتخابی نباید بیشتر از {MAX_RANGE_SIZE} پیام باشد."
    return None


def parse_id_list(raw: str) -> tuple[list[int] | None, str | None]:
    raw = raw.strip()
    if not raw:
        return None, "ورودی خالی است."
    parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
    ids: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None, f"مقدار «{part}» یک Message ID معتبر نیست."
        ids.append(int(part))
    if not ids:
        return None, "هیچ Message ID معتبری یافت نشد."
    if len(ids) > MAX_RANGE_SIZE:
        return None, f"حداکثر {MAX_RANGE_SIZE} پیام در هر عملیات مجاز است."
    return sorted(set(ids)), None
