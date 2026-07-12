from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.handlers.booking import booking
from app.handlers.profile import profile

from app.keyboards.category import category_menu
from app.keyboards.master import master_menu
from app.keyboards.date import date_menu


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📅 Записаться":
        await booking(update, context)

    elif text == "🏙 Бишкек":
        context.user_data["city"] = "Бишкек"

        await update.message.reply_text(
            "✅ Вы выбрали Бишкек.\n\n📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )

    elif text == "🏙 Ош":
        context.user_data["city"] = "Ош"

        await update.message.reply_text(
            "✅ Вы выбрали Ош.\n\n📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )

    elif text == "🏙 Джалал-Абад":
        context.user_data["city"] = "Джалал-Абад"

        await update.message.reply_text(
            "✅ Вы выбрали Джалал-Абад.\n\n📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )

    elif text == "💇 Волосы":
        context.user_data["category"] = "hair"

        await update.message.reply_text(
            "💇 Выберите мастера",
            reply_markup=master_menu(),
        )

    elif text == "💅 Маникюр":
        context.user_data["category"] = "nails"

        await update.message.reply_text(
            "💅 Выберите мастера",
            reply_markup=master_menu(),
        )

    elif text == "👁 Ресницы":
        context.user_data["category"] = "lashes"

        await update.message.reply_text(
            "👁 Выберите мастера",
            reply_markup=master_menu(),
        )

    elif text == "💆 Массаж":
        context.user_data["category"] = "massage"

        await update.message.reply_text(
            "💆 Выберите мастера",
            reply_markup=master_menu(),
        )

    elif text == "👩 Айжан ⭐4.9":
        context.user_data["master"] = "Айжан"

        await update.message.reply_text(
            "📅 Выберите дату",
            reply_markup=date_menu(),
        )

    elif text == "👩 Алина ⭐5.0":
        context.user_data["master"] = "Алина"

        await update.message.reply_text(
            "📅 Выберите дату",
            reply_markup=date_menu(),
        )

    elif text == "👨 Азамат ⭐4.8":
        context.user_data["master"] = "Азамат"

        await update.message.reply_text(
            "📅 Выберите дату",
            reply_markup=date_menu(),
        )

    elif text == "👤 Личный кабинет":
        await profile(update, context)

    elif text == "❤️ Избранное":
        await update.message.reply_text(
            "❤️ У вас пока нет избранных мастеров."
        )

    elif text == "⚙️ Настройки":
        await update.message.reply_text(
            "⚙️ Раздел настроек скоро появятся."
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
