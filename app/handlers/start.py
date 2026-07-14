from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from app.keyboards.main import main_menu

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Старт работает!",
        reply_markup=main_menu(),
    )

start_handler = CommandHandler("start", start)
