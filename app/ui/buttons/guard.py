from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.guard_profile import MODES, TOPICS


def button(text, action):
    return InlineKeyboardButton(text, callback_data=f"guard:{action}")


def guard_menu(profile):
    rows = [
        [button(f"{label}: {MODES[profile['sensitivity'][name]]}", f"cycle:{name}")]
        for name, label in TOPICS.items()
    ]
    rows += [
        [button("📤 دریافت فایل تنظیمات", "export"), button("📥 بارگذاری فایل", "import")],
        [InlineKeyboardButton("‹ تنظیمات", callback_data="menu:settings")],
    ]
    return InlineKeyboardMarkup(rows)


def guard_confirm(token):
    return InlineKeyboardMarkup(
        [[button("✅ اعمال تنظیمات", f"apply:{token}"), button("لغو", "show")]]
    )
