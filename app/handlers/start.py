from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Добро пожаловать в BTT!\n\n"
        "Платформа успешно запущена."
    )


start_handler = CommandHandler("start", start)
