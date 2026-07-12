from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.handlers.booking import booking
from app.handlers.profile import profile


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📅 Записаться":
        await booking(update, context)

    elif text == "👤 Личный кабинет":
        await profile(update, context)

    elif text == "❤️ Избранное":
        await update.message.reply_text(
            "❤️ У вас пока нет избранных мастеров."
        )

    elif text == "⚙️ Настройки":
        await update.message.reply_text(
            "⚙️ Раздел настроек скоро появится."
        )

    elif text == "🏠 Главное меню":
        await update.message.reply_text(
            "Вы уже находитесь в главном меню."
        )

    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню."
        )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)
