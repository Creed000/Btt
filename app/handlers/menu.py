from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.handlers.booking import booking
from app.handlers.profile import profile

from app.keyboards.category import category_menu
from app.keyboards.master import master_menu
from app.keyboards.date import date_menu
from app.keyboards.time import time_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.main import main_menu
from app.database.bookings import create_booking
from datetime import datetime

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "📅 Записаться":
        await booking(update, context)
    elif text == "👤 Личный кабинет":
        await profile(update, context)

    elif text == "🔍 Найти мастера":
        await booking(update, context)

    elif text == "💼 Стать мастером":
        await update.message.reply_text(
            "💼 Регистрация мастера появится в ближайшем обновлении.",
            reply_markup=main_menu(),
        )

    elif text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ Добро пожаловать в BTT!\n\n"
            "📅 Записаться — запись к мастеру\n"
            "🔍 Найти мастера — поиск по каталогу\n"
            "👤 Личный кабинет — ваши записи\n"
            "⚙️ Настройки — настройки аккаунта",
            reply_markup=main_menu(),
        )
        
    elif text == "⚙️ Настройки":
        await update.message.reply_text(
            "⚙️ Настройки появятся в следующем обновлении."
        )

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

    elif text.startswith("👤"):

        name = text.split("⭐")[0]
        name = name.replace("👤", "").strip()

        context.user_data["master"] = name

        await update.message.reply_text(
            "📅 Выберите дату",
            reply_markup=date_menu(),
        )
    elif text == "📅 Сегодня":
        context.user_data["date"] = "Сегодня"

        await update.message.reply_text(
            "🕒 Выберите время",
            reply_markup=time_menu(),
        )

    elif text == "📅 Завтра":
        context.user_data["date"] = "Завтра"

        await update.message.reply_text(
            "🕒 Выберите время",
            reply_markup=time_menu(),
        )

    elif text == "📅 Послезавтра":
        context.user_data["date"] = "Послезавтра"

        await update.message.reply_text(
            "🕒 Выберите время",
            reply_markup=time_menu(),
        )

    elif text in [
        "🕘 09:00",
        "🕙 10:00",
        "🕚 11:00",
        "🕛 12:00",
        "🕐 13:00",
        "🕑 14:00",
        "🕒 15:00",
        "🕓 16:00",
        "🕔 17:00",
        "🕕 18:00",
    ]:

        context.user_data["time"] = text

        await update.message.reply_text(
            f"""📋 Подтверждение записи

    🏙 Город: {context.user_data.get('city')}
    📂 Категория: {context.user_data.get('category')}
    👤 Мастер: {context.user_data.get('master')}
    📅 Дата: {context.user_data.get('date')}
    🕒 Время: {context.user_data.get('time')}

    Подтвердить запись?""",
            reply_markup=confirm_menu(),
        )

    elif text == "✅ Подтвердить":

        booking_time = (
    f"{context.user_data['date']} "
    f"{context.user_data['time']}"
)

        create_booking(
            client_id=update.effective_user.id,
            service_id=1,
            booking_time=booking_time,
        )

        context.user_data.clear()

        await update.message.reply_text(
            "🎉 Запись успешно создана!\n\n"
            "Спасибо за использование BTT.",
            reply_markup=main_menu(),
        )

    elif text == "❌ Отменить":

        context.user_data.clear()

        await update.message.reply_text(
            "❌ Запись отменена.",
            reply_markup=main_menu(),
        )

    
    elif text == "⬅️ Назад":
        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=main_menu(),
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню."
        )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)
