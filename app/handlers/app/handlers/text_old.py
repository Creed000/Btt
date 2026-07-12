from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.handlers.booking import booking
from app.keyboards.category import category_menu
from app.handlers.profile import profile

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    # Главное меню
    if text == "📅 Записаться":
        await booking(update, context)

    elif text == "👤 Личный кабинет":
        await profile(update, context)

    elif text == "❤️ Избранное":
        await update.message.reply_text("❤️ Избранное")

    elif text == "⚙️ Настройки":
        await update.message.reply_text("⚙️ Настройки")

    # Выбор города
    elif text in [
        "🏙 Бишкек",
        "🏙 Ош",
        "🏙 Джалал-Абад",
    ]:

        context.user_data["city"] = text

        await update.message.reply_text(
            f"✅ Вы выбрали: {text}\n\n"
            "📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )

    # Категории
    elif text == "💇 Волосы":
        from app.handlers.menu import menu_handler
        await menu_handler(update, context)

    elif text == "💅 Маникюр":
        from app.handlers.menu import menu_handler
        await menu_handler(update, context)

    elif text == "👁 Ресницы":
        from app.handlers.menu import menu_handler
        await menu_handler(update, context)

    elif text == "💆 Массаж":
        from app.handlers.menu import menu_handler
        await menu_handler(update, context)

    # Назад
    elif text == "⬅️ Назад":

        from app.keyboards.client import client_menu

        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=client_menu(),
        )

    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню."
        )


text_message_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    text_handler,
)
