from telegram import KeyboardButton, ReplyKeyboardMarkup


ADMIN_ROLES = {
    "admin",
    "owner",
}


def main_menu(
    role: str | None = None,
) -> ReplyKeyboardMarkup:
    keyboard = [
        [
            KeyboardButton("📅 Записаться"),
            KeyboardButton("🔍 Найти мастера"),
        ],
        [
            KeyboardButton("👤 Личный кабинет"),
            KeyboardButton("💼 Стать мастером"),
        ],
        [
            KeyboardButton("ℹ️ Помощь"),
            KeyboardButton("⚙️ Настройки"),
        ],
    ]

    if role != "owner":
        keyboard.append(
            [KeyboardButton("🏢 Создать салон")]
        )

    if role in ADMIN_ROLES:
        keyboard.append(
            [KeyboardButton("👑 Админ-панель")]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )
