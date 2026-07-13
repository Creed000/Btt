from telegram import Update
from telegram.ext import (
    ContextTypes,
    MessageHandler,
    filters,
)

from app.keyboards.city import city_menu


async def booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Кнопка главного меню
    if text == "📅 Записаться":
        await update.message.reply_text(
            "📅 Выберите город",
            reply_markup=city_menu(),
        )
        return


booking_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    booking,
)
