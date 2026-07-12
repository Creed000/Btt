from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards.city import city_menu


async def booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 Выберите город",
        reply_markup=city_menu(),
    )
