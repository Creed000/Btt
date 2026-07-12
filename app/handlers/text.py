from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.handlers.booking import booking


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📅 Записаться":
        await booking(update, context)

    elif text == "👤 Личный кабинет":
        await update.message.reply_text("Личный кабинет")

    elif text == "❤️ Избранное":
        await update.message.reply_text("Избранное")

    elif text == "⚙️ Настройки":
        await update.message.reply_text("Настройки")

    else:
        await update.message.reply_text("Используйте кнопки меню.")


text_message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    text_handler,
)
