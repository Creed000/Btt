from telegram import Update
from telegram.ext import ContextTypes


async def booking(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "📅 Онлайн-запись\n\n"
        "Выберите город."

    )
