from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.user import User


def settings_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🌐 Язык")],
            [KeyboardButton("🕒 Часовой пояс")],
            [KeyboardButton("🔔 Уведомления")],
            [KeyboardButton("👤 Личный кабинет")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Настройки аккаунта",
    )


async def open_settings_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        language_names = {
            "ru": "Русский",
            "ky": "Кыргызча",
            "en": "English",
        }

        language = language_names.get(
            user.language,
            user.language or "Русский",
        )

        await update.message.reply_text(
            "⚙️ Настройки аккаунта\n\n"
            f"🌐 Язык: {language}\n"
            f"🕒 Часовой пояс: {user.timezone}\n"
            f"🔔 Уведомления: включены\n\n"
            "Выберите раздел:",
            reply_markup=settings_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть настройки.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
