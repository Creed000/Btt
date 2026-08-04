from telegram import KeyboardButton, ReplyKeyboardMarkup

from app.services.access_control import is_platform_admin


def main_menu(
    role: str | None = None,
    telegram_id: int | None = None,
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

    # owner — владелец конкретного салона.
    if role == "owner":
        keyboard.append(
            [KeyboardButton("🏢 Кабинет салона")]
        )
    else:
        keyboard.append(
            [KeyboardButton("🏢 Создать салон")]
        )

    # Показываем кнопку системному admin.
    # Если Telegram ID передан, дополнительно проверяем настройки Railway.
    #
    # Сам доступ всё равно защищён внутри admin_panel.py через
    # can_manage_platform(), поэтому ручной ввод текста не даст прав.
    has_admin_button = (
        role == "admin"
        or (
            telegram_id is not None
            and is_platform_admin(telegram_id)
        )
    )

    if has_admin_button:
        keyboard.append(
            [KeyboardButton("👑 Админ-панель")]
        )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )
