from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_PRIMARY, STYLE_SUCCESS, _cb, _copy


def main_menu(
    source_ready: bool,
    destination_ready: bool,
    auto_forward_enabled: bool = False,
    source_id: int | None = None,
    destination_id: int | None = None,
) -> InlineKeyboardMarkup:
    ready = source_ready and destination_ready

    rows: list[list[InlineKeyboardButton]] = [
        [
            _cb(
                "📥 مبدأ" if not source_ready else "✅ مبدأ",
                "menu:source",
                style=STYLE_SUCCESS if source_ready else STYLE_PRIMARY,
            ),
            _cb(
                "📤 مقصد" if not destination_ready else "✅ مقصد",
                "menu:destination",
                style=STYLE_SUCCESS if destination_ready else STYLE_PRIMARY,
            ),
        ]
    ]

    copy_row: list[InlineKeyboardButton] = []
    if source_id is not None:
        copy_row.append(_copy("📋 ID مبدأ", source_id))
    if destination_id is not None:
        copy_row.append(_copy("📋 ID مقصد", destination_id))
    if copy_row:
        rows.append(copy_row)

    if ready:
        rows.append([_cb("🚀 انتقال پیام‌ها", "menu:transfer", style=STYLE_SUCCESS)])
        rows.append(
            [
                _cb(
                    "🟢 Auto-Forward روشن" if auto_forward_enabled else "⚪ Auto-Forward خاموش",
                    "menu:auto_toggle",
                    style=STYLE_SUCCESS if auto_forward_enabled else STYLE_PRIMARY,
                )
            ]
        )

    rows.extend(
        [
            [
                _cb("🕘 اخیر", "menu:recent"),
                _cb("📊 آمار", "menu:stats", style=STYLE_PRIMARY),
            ],
            [
                _cb("⚙️ تنظیمات", "menu:settings"),
                _cb("❓ راهنما", "menu:help"),
            ],
        ]
    )

    return InlineKeyboardMarkup(rows)
