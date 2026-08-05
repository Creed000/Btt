from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.settings_panel import settings_menu
from app.models.user import User


TIMEZONE_BUTTONS = {
    "🇰🇬 Бишкек · UTC+6": "Asia/Bishkek",
    "🇳🇱 Амстердам · Europe/Amsterdam": "Europe/Amsterdam",
    "🇷🇺 Москва · UTC+3": "Europe/Moscow",
    "🇰🇿 Алматы · UTC+5": "Asia/Almaty",
    "🇺🇿 Ташкент · UTC+5": "Asia/Tashkent",
}


def timezone_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🇰🇬 Бишкек · UTC+6")],
            [KeyboardButton("🇳🇱 Амстердам · Europe/Amsterdam")],
            [KeyboardButton("🇷🇺 Москва · UTC+3")],
            [KeyboardButton("🇰🇿 Алматы · UTC+5")],
            [KeyboardButton("🇺🇿 Ташкент · UTC+5")],
            [KeyboardButton("⬅️ Назад к настройкам")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите часовой пояс",
    )


async def open_timezone_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "🕒 Выберите часовой пояс:",
        reply_markup=timezone_menu(),
    )


async def change_user_timezone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text = update.message.text.strip()

    timezone_name = TIMEZONE_BUTTONS.get(text)

    if timezone_name is None:
        return False

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        await update.message.reply_text(
            "❌ Этот часовой пояс недоступен.",
            reply_markup=timezone_menu(),
        )
        return True

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start."
            )
            return True

        user.timezone = timezone_name
        db.commit()

        await update.message.reply_text(
            "✅ Часовой пояс сохранён:\n"
            f"{timezone_name}",
            reply_markup=settings_menu(),
        )

        return True

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось сохранить часовой пояс.",
            reply_markup=settings_menu(),
        )

        return True

    finally:
        db.close()
