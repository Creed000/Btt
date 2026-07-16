from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Поддержка кнопок с разными эмодзи и без них
    normalized = (
        text.replace("🔍", "")
            .replace("🔎", "")
            .strip()
    )

    if normalized != "Найти мастера":
        return

    await update.message.reply_text(
        "🔎 Поиск мастеров\n\n"
        "Функция находится в разработке."
    )


search_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    search,
)
