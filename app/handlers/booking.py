from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app.keyboards.city import city_menu


async def booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text != "📅 Записаться":
        return

    await update.message.reply_text(
        "📅 Выберите город",
        reply_markup=city_menu(),
    )


booking_handler = MessageHandler(
    filters.Regex(r"^📅 Записаться$"),
    booking,
)
