from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text != "⚙️ Настройки":
        return

    await update.message.reply_text(
        "⚙️ Настройки\n\n"
        "Выберите действие:\n\n"
        "🌐 Язык\n"
        "🔔 Уведомления\n"
        "🌙 Тема\n"
        "👤 Профиль\n\n"
        "⚠️ Раздел находится в разработке."
    )


settings_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    settings,
)
