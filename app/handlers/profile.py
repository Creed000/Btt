from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.repositories.user_repository import UserRepository


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()

    try:
        user = UserRepository.get_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if not user:
            await update.message.reply_text(
                "❌ Вы еще не зарегистрированы.\nВведите /start."
            )
            return

        text = (
            "👤 Личный кабинет\n\n"
            f"🆔 Telegram ID: {user.telegram_id}\n"
            f"👤 Имя: {user.first_name}\n"
            f"📛 Фамилия: {user.last_name or '-'}\n"
            f"🌐 Username: @{user.username or '-'}"
        )

        await update.message.reply_text(text)

    finally:
        db.close()


profile_handler = CommandHandler("profile", profile)
