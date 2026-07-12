from telegram import Update
from telegram.ext import MessageHandler, ContextTypes, filters

from app.handlers.profile import profile


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "👤 Личный кабинет":
        await profile(update, context)
        return

    await update.message.reply_text("Эта функция пока находится в разработке.")
    

menu_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, menu)
