from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.models.user import User
from app.handlers.settings_panel import settings_menu


LANGUAGE_BUTTONS = {
    "🇷🇺 Русский": "ru",
    "🇰🇬 Кыргызча": "ky",
    "🇬🇧 English": "en",
}

LANGUAGE_NAMES = {
    "ru": "Русский",
    "ky": "Кыргызча",
    "en": "English",
}


def language_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🇷🇺 Русский")],
            [KeyboardButton("🇰🇬 Кыргызча")],
            [KeyboardButton("🇬🇧 English")],
            [KeyboardButton("⬅️ Назад к настройкам")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите язык",
    )


async def open_language_settings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "🌐 Выберите язык интерфейса:",
        reply_markup=language_menu(),
    )


async def change_user_language(
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

    if text == "⬅️ Назад к настройкам":
        await update.message.reply_text(
            "⚙️ Настройки аккаунта",
            reply_markup=settings_menu(),
        )
        return True

    language_code = LANGUAGE_BUTTONS.get(text)

    if language_code is None:
        return False

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

        user.language = language_code
        db.commit()

        await update.message.reply_text(
            "✅ Язык сохранён: "
            f"{LANGUAGE_NAMES[language_code]}",
            reply_markup=settings_menu(),
        )

        return True

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось сохранить язык.",
            reply_markup=settings_menu(),
        )

        return True

    finally:
        db.close()
