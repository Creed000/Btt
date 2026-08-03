from datetime import date, datetime, timedelta

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.handlers.booking import booking
from app.handlers.master_bookings import (
    change_master_booking_status,
    show_master_bookings,
)
from app.handlers.master_panel import become_master
from app.handlers.master_city import begin_master_city_selection, process_master_city_selection
from app.handlers.profile import profile
from app.handlers.search import search
from app.handlers.service_manager import (
    begin_add_service,
    delete_master_service,
    process_service_creation,
    show_master_services,
    toggle_master_booking,
)
from app.keyboards.available_time import available_time_menu
from app.keyboards.category import category_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.date import date_menu
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.keyboards.service import service_menu
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User
from app.services.availability import get_available_slots


CITY_BUTTONS = {
    "🏙 Бишкек": "Бишкек",
    "🏙 Ош": "Ош",
    "🏙 Джалал-Абад": "Джалал-Абад",
}

CATEGORY_BUTTONS = {
    "💇 Волосы": "Волосы",
    "💅 Маникюр": "Маникюр",
    "👁 Ресницы": "Ресницы",
    "💆 Массаж": "Массаж",
}

DATE_BUTTONS = {
    "📅 Сегодня": 0,
    "📅 Завтра": 1,
    "📅 Послезавтра": 2,
}


def clear_booking_data(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
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


async def cancel_client_booking(
    update: Update,
    booking_id: int,
) -> None:
    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(),
            )
            return

        booking_item = db.scalar(
            select(Booking).where(
                Booking.id == booking_id,
                Booking.client_id == user.id,
            )
        )

        if booking_item is None:
            await update.message.reply_text(
                "❌ Запись не найдена или принадлежит другому пользователю.",
                reply_markup=main_menu(),
            )
            return

        if booking_item.status == "cancelled":
            await update.message.reply_text(
                "ℹ️ Эта запись уже отменена.",
                reply_markup=main_menu(),
            )
            return

        if booking_item.status == "completed":
            await update.message.reply_text(
                "❌ Завершённую запись отменить нельзя.",
                reply_markup=main_menu(),
            )
            return

        booking_item.status = "cancelled"
        db.commit()

        await update.message.reply_text(
            f"✅ Запись #{booking_id} отменена.",
            reply_markup=main_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отменить запись. Попробуйте позже.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip()

    if await process_master_city_selection(update, context):
        return

    # Продолжаем незавершённое создание услуги.
    if context.user_data.get("service_creation"):
        handled = await process_service_creation(
            update,
            context,
        )
        if handled:
            return

    # Кабинет мастера: услуги.
    if text == "➕ Добавить услугу":
        await begin_add_service(update, context)
        return

    if text == "📋 Мои услуги":
        await show_master_services(update, context)
        return

    if text.startswith("🗑 Удалить услугу #"):
        try:
            service_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер услуги.",
                reply_markup=main_menu(),
            )
            return

        await delete_master_service(
            update,
            context,
            service_id,
        )
        return

    if text == "🏙 Мой город":
        await begin_master_city_selection(update, context)
        return

    if text == "⛔ Выключить запись":
        await toggle_master_booking(
            update,
            context,
            enabled=False,
        )
        return

    if text == "✅ Включить запись":
        await toggle_master_booking(
            update,
            context,
            enabled=True,
        )
        return

    # Кабинет мастера: записи.
    if text == "📅 Мои записи":
        await show_master_bookings(update, context)
        return

    if text.startswith("✅ Подтвердить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="confirmed",
        )
        return

    if text.startswith("🏁 Завершить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="completed",
        )
        return

    if text.startswith("❌ Отменить заявку #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="cancelled",
        )
        return

    # Клиент отменяет свою запись.
    if text.startswith("❌ Отменить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(),
            )
            return

        await cancel_client_booking(update, booking_id)
        return

    # Главное меню.
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
        await become_master(update, context)
        return

    if text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ Добро пожаловать в BTT!\n\n"
            "📅 Записаться — запись к мастеру\n"
            "🔍 Найти мастера — поиск по каталогу\n"
            "👤 Личный кабинет — ваши записи\n"
            "💼 Стать мастером — кабинет мастера\n"
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

    # Запись клиента: город.
    if text in CITY_BUTTONS:
        context.user_data["city"] = CITY_BUTTONS[text]

        await update.message.reply_text(
            f"✅ Город: {CITY_BUTTONS[text]}\n\n"
            "📂 Теперь выберите категорию.",
            reply_markup=category_menu(),
        )
        return

    # Запись клиента: категория.
    if text in CATEGORY_BUTTONS:
        selected_category = CATEGORY_BUTTONS[text]
        selected_city = context.user_data.get("city")

        if selected_city is None:
            await update.message.reply_text(
                "⚠️ Сначала выберите город.",
                reply_markup=main_menu(),
            )
            return

        context.user_data["category"] = selected_category

        await update.message.reply_text(
            "👤 Выберите мастера.",
            reply_markup=master_menu(
                city_name=selected_city,
                category_name=selected_category,
            ),
        )
        return

    # Запись клиента: мастер.
    if text.startswith("👤") and "#" in text:
        try:
            master_id = int(
                text.split("#", 1)[1].split()[0]
            )
            master_name = (
                text.split("·", 1)[0]
                .replace("👤", "")
                .strip()
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "Не удалось определить мастера. Выберите его кнопкой."
            )
            return

        db = SessionLocal()

        try:
            services = list(
                db.scalars(
                    select(Service)
                    .where(Service.master_id == master_id)
                    .order_by(Service.title)
                ).all()
            )
        finally:
            db.close()

        if not services:
            clear_booking_data(context)

            await update.message.reply_text(
                "У этого мастера пока нет добавленных услуг.",
                reply_markup=main_menu(),
            )
            return

        context.user_data["master_id"] = master_id
        context.user_data["master_name"] = master_name
        context.user_data.pop("service_id", None)
        context.user_data.pop("service_title", None)

        await update.message.reply_text(
            f"✅ Мастер: {master_name}\n\n"
            "💼 Теперь выберите услугу:",
            reply_markup=service_menu(services),
        )
        return

    # Запись клиента: услуга.
    if text.startswith("💼") and "#" in text:
        try:
            service_id = int(
                text.split("#", 1)[1].split()[0]
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "Не удалось определить услугу. Выберите её кнопкой."
            )
            return

        master_id = context.user_data.get("master_id")

        if master_id is None:
            await update.message.reply_text(
                "Сначала выберите мастера.",
                reply_markup=main_menu(),
            )
            return

        db = SessionLocal()

        try:
            service = db.scalar(
                select(Service).where(
                    Service.id == service_id,
                    Service.master_id == master_id,
                )
            )
        finally:
            db.close()

        if service is None:
            clear_booking_data(context)

            await update.message.reply_text(
                "Услуга не найдена или не принадлежит выбранному мастеру.",
                reply_markup=main_menu(),
            )
            return

        context.user_data["service_id"] = service.id
        context.user_data["service_title"] = service.title

        await update.message.reply_text(
            f"✅ Услуга: {service.title}\n"
            f"⏱ Длительность: {service.duration} мин.\n"
            f"💰 Цена: {service.price}\n\n"
            "📅 Выберите дату.",
            reply_markup=date_menu(),
        )
        return

    if text == "Услуг пока нет":
        clear_booking_data(context)

        await update.message.reply_text(
            "У выбранного мастера пока нет доступных услуг.",
            reply_markup=main_menu(),
        )
        return

    # Запись клиента: дата и свободные слоты.
    if text in DATE_BUTTONS:
        selected_date = date.today() + timedelta(
            days=DATE_BUTTONS[text]
        )

        master_id = context.user_data.get("master_id")
        service_id = context.user_data.get("service_id")

        if master_id is None or service_id is None:
            clear_booking_data(context)

            await update.message.reply_text(
                "⚠️ Сначала выберите мастера и услугу.",
                reply_markup=main_menu(),
            )
            return

        db = SessionLocal()

        try:
            slots = get_available_slots(
                db=db,
                master_id=master_id,
                service_id=service_id,
                booking_date=selected_date,
            )
        except ValueError as error:
            clear_booking_data(context)

            await update.message.reply_text(
                f"⚠️ {error}",
                reply_markup=main_menu(),
            )
            return
        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "❌ Не удалось загрузить свободное время.",
                reply_markup=main_menu(),
            )
            return
        finally:
            db.close()

        context.user_data["booking_date"] = selected_date

        await update.message.reply_text(
            f"✅ Дата: {selected_date.strftime('%d.%m.%Y')}\n\n"
            "🕒 Выберите свободное время.",
            reply_markup=available_time_menu(slots),
        )
        return

    if text == "Свободного времени нет":
        await update.message.reply_text(
            "На выбранную дату свободных слотов нет. "
            "Выберите другую дату.",
            reply_markup=date_menu(),
        )
        return

    # Запись клиента: время.
    if text.startswith("🕒 "):
        try:
            selected_time = datetime.strptime(
                text.replace("🕒 ", "", 1),
                "%H:%M",
            ).time()
        except ValueError:
            await update.message.reply_text(
                "Не удалось определить время. Выберите слот кнопкой."
            )
            return

        context.user_data["booking_time"] = selected_time

        booking_date = context.user_data.get("booking_date")
        date_text = (
            booking_date.strftime("%d.%m.%Y")
            if booking_date
            else "—"
        )

        await update.message.reply_text(
            "📋 Подтверждение записи\n\n"
            f"🏙 Город: {context.user_data.get('city', '—')}\n"
            f"📂 Категория: {context.user_data.get('category', '—')}\n"
            f"👤 Мастер: {context.user_data.get('master_name', '—')}\n"
            f"💼 Услуга: {context.user_data.get('service_title', '—')}\n"
            f"📅 Дата: {date_text}\n"
            f"🕒 Время: {selected_time.strftime('%H:%M')}\n\n"
            "Подтвердить запись?",
            reply_markup=confirm_menu(),
        )
        return

    # Запись клиента: подтверждение.
    if text == "✅ Подтвердить":
        required_fields = (
            "master_id",
            "service_id",
            "booking_date",
            "booking_time",
        )

        if not all(
            context.user_data.get(field)
            for field in required_fields
        ):
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
            clear_booking_data(context)

            await update.message.reply_text(
                f"⚠️ {error}",
                reply_markup=main_menu(),
            )
            return
        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "❌ Не удалось создать запись. Попробуйте ещё раз.",
                reply_markup=main_menu(),
            )
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
            "❌ Создание записи отменено.",
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

    if text in {
        "Мастеров пока нет",
        "Подходящих мастеров нет",
    }:
        await update.message.reply_text(
            "По выбранному городу и категории подходящих мастеров пока нет.",
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
