from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Поиск мастеров")

search_handler = MessageHandler(
    filters.Regex("^🔍 Найти мастера$"),
    search,
)
