from datetime import date, datetime, timedelta

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.handlers.booking import booking
from app.handlers.profile import profile
from app.handlers.search import search
from app.keyboards.category import category_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.date import date_menu
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.keyboards.time import time_menu
from app.models.service import Service


CITY_BUTTONS = {
    "🏙 Бишкек": "Бишкек",
    "🏙 Ош": "Ош",
    "🏙 Джалал-Абад": "Джалал-Абад",
}

CATEGORY_BUTTONS = {
    "💇 Волосы": "hair",
    "💅 Маникюр": "nails",
    "👁 Ресницы": "lashes",
    "💆 Массаж": "massage",
}

DATE_BUTTONS = {
    "📅 Сегодня": 0,
    "📅 Завтра": 1,
    "📅 Послезавтра": 2,
}

TIME_BUTTONS = {
    "🕘 09:00": "09:00",
    "🕙 10:00": "10:00",
    "🕚 11:00": "11:00",
    "🕛 12:00": "12:00",
    "🕐 13:00": "13:00",
    "🕑 14:00": "14:00",
    "🕒 15:00": "15:00",
    "🕓 16:00": "16:00",
}


def clear_booking_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "city",
        "category",
        "master_id",
        "master_name",
        "service_id",
        "service_title",
        "booking_date",
        "booking_time",
    ):
        context.user_data.pop(key, None)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip()

    if text == "📅 Записаться":
        clear_booking_data(context)
        await booking(update, context)
        return

    if text == "👤 Личный кабинет":
        await profile(update, context)
        return

    if text == "🔍 Найти мастера":
        await search(update, context)
        return

    if text == "💼 Стать мастером":
        await update.message.reply_text(
            "💼 Регистрация мастера появится в следующем этапе.",
            reply_markup=main_menu(),
        )
        return

    if text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ Добро пожаловать в BTT!\n\n"
            "📅 Записаться — запись к мастеру\n"
            "🔍 Найти мастера — поиск по каталогу\n"
            "👤 Личный кабинет — ваши записи\n"
            "💼 Стать мастером — регистрация мастера\n"
            "⚙️ Настройки — настройки аккаунта",
            reply_markup=main_menu(),
        )
        return

    if text == "⚙️ Настройки":
        await update.message.reply_text(
            "⚙️ Настройки появятся в следующем этапе.",
            reply_markup=main_menu(),
        )
        return

    if text in CITY_BUTTONS:
        context.user_data["city"] = CITY_BUTTONS[text]

        await update.message.reply_text(
            f"✅ Город: {CITY_BUTTONS[text]}\n\n"
            "📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )
        return

    if text in CATEGORY_BUTTONS:
        context.user_data["category"] = CATEGORY_BUTTONS[text]

        await update.message.reply_text(
            "👤 Выберите мастера.",
            reply_markup=master_menu(),
        )
        return

    if text.startswith("👤") and "#" in text:
        try:
            master_id = int(text.split("#", 1)[1].split()[0])
            master_name = (
                text.split("·", 1)[0]
                .replace("👤", "")
                .strip()
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "Не удалось определить мастера. Выберите мастера кнопкой."
            )
            return

        db = SessionLocal()
        try:
            service = db.scalar(
                select(Service)
                .where(Service.master_id == master_id)
                .order_by(Service.id)
            )
        finally:
            db.close()

        if service is None:
            await update.message.reply_text(
                "У этого мастера пока нет добавленных услуг.",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return

        context.user_data["master_id"] = master_id
        context.user_data["master_name"] = master_name
        context.user_data["service_id"] = service.id
        context.user_data["service_title"] = service.title

        await update.message.reply_text(
            f"✅ Мастер: {master_name}\n"
            f"💼 Услуга: {service.title}\n\n"
            "📅 Выберите дату.",
            reply_markup=date_menu(),
        )
        return

    if text in DATE_BUTTONS:
        selected_date = date.today() + timedelta(days=DATE_BUTTONS[text])
        context.user_data["booking_date"] = selected_date

        await update.message.reply_text(
            f"✅ Дата: {selected_date.strftime('%d.%m.%Y')}\n\n"
            "🕒 Выберите время.",
            reply_markup=time_menu(),
        )
        return

    if text in TIME_BUTTONS:
        selected_time = datetime.strptime(
            TIME_BUTTONS[text],
            "%H:%M",
        ).time()

        context.user_data["booking_time"] = selected_time

        await update.message.reply_text(
            "📋 Подтверждение записи\n\n"
            f"🏙 Город: {context.user_data.get('city', '—')}\n"
            f"📂 Категория: {context.user_data.get('category', '—')}\n"
            f"👤 Мастер: {context.user_data.get('master_name', '—')}\n"
            f"💼 Услуга: {context.user_data.get('service_title', '—')}\n"
            f"📅 Дата: "
            f"{context.user_data.get('booking_date').strftime('%d.%m.%Y') if context.user_data.get('booking_date') else '—'}\n"
            f"🕒 Время: {selected_time.strftime('%H:%M')}\n\n"
            "Подтвердить запись?",
            reply_markup=confirm_menu(),
        )
        return

    if text == "✅ Подтвердить":
        required_fields = (
            "master_id",
            "service_id",
            "booking_date",
            "booking_time",
        )

        if not all(context.user_data.get(field) for field in required_fields):
            clear_booking_data(context)
            await update.message.reply_text(
                "⚠️ Данные записи заполнены не полностью. Начните заново.",
                reply_markup=main_menu(),
            )
            return

        try:
            created_booking = create_booking(
                telegram_id=update.effective_user.id,
                master_id=context.user_data["master_id"],
                service_id=context.user_data["service_id"],
                booking_date=context.user_data["booking_date"],
                booking_time=context.user_data["booking_time"],
            )
        except ValueError as error:
            await update.message.reply_text(
                f"⚠️ {error}",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return
        except Exception:
            await update.message.reply_text(
                "❌ Не удалось создать запись. Попробуйте ещё раз.",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return

        clear_booking_data(context)

        await update.message.reply_text(
            "🎉 Запись успешно создана!\n\n"
            f"Номер записи: {created_booking.id}",
            reply_markup=main_menu(),
        )
        return

    if text == "❌ Отменить":
        clear_booking_data(context)

        await update.message.reply_text(
            "❌ Запись отменена.",
            reply_markup=main_menu(),
        )
        return

    if text == "⬅️ Назад":
        clear_booking_data(context)

        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=main_menu(),
        )
        return

    if text == "Мастеров пока нет":
        await update.message.reply_text(
            "В системе пока нет доступных мастеров.",
            reply_markup=main_menu(),
        )
        return

    await update.message.reply_text(
        "Пожалуйста, используйте кнопки меню.",
        reply_markup=main_menu(),
    )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)
