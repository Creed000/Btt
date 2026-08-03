from datetime import date, datetime, timedelta

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.handlers.booking import booking
from app.handlers.master_panel import become_master
from app.handlers.master_bookings import (
    change_master_booking_status,
    show_master_bookings,
)
from app.handlers.profile import profile
from app.handlers.search import search
from app.handlers.service_manager import (
    begin_add_service,
    process_service_creation,
    show_master_services,
    toggle_master_booking,
)
from app.keyboards.category import category_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.date import date_menu
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.keyboards.service import service_menu
from app.keyboards.available_time import available_time_menu
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User
from app.services.availability import get_available_slots


CITY_BUTTONS = {
    "ð ÐÐ¸ÑÐºÐµÐº": "ÐÐ¸ÑÐºÐµÐº",
    "ð ÐÑ": "ÐÑ",
    "ð ÐÐ¶Ð°Ð»Ð°Ð»-ÐÐ±Ð°Ð´": "ÐÐ¶Ð°Ð»Ð°Ð»-ÐÐ±Ð°Ð´",
}

CATEGORY_BUTTONS = {
    "ð ÐÐ¾Ð»Ð¾ÑÑ": "hair",
    "ð ÐÐ°Ð½Ð¸ÐºÑÑ": "nails",
    "ð Ð ÐµÑÐ½Ð¸ÑÑ": "lashes",
    "ð ÐÐ°ÑÑÐ°Ð¶": "massage",
}

DATE_BUTTONS = {
    "ð Ð¡ÐµÐ³Ð¾Ð´Ð½Ñ": 0,
    "ð ÐÐ°Ð²ÑÑÐ°": 1,
    "ð ÐÐ¾ÑÐ»ÐµÐ·Ð°Ð²ÑÑÐ°": 2,
}

TIME_BUTTONS = {
    "ð 09:00": "09:00",
    "ð 10:00": "10:00",
    "ð 11:00": "11:00",
    "ð 12:00": "12:00",
    "ð 13:00": "13:00",
    "ð 14:00": "14:00",
    "ð 15:00": "15:00",
    "ð 16:00": "16:00",
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
                "â ÐÐ¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½. ÐÑÐ¿ÑÐ°Ð²ÑÑÐµ /start.",
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
                "â ÐÐ°Ð¿Ð¸ÑÑ Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð° Ð¸Ð»Ð¸ Ð¿ÑÐ¸Ð½Ð°Ð´Ð»ÐµÐ¶Ð¸Ñ Ð´ÑÑÐ³Ð¾Ð¼Ñ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ.",
                reply_markup=main_menu(),
            )
            return

        if booking_item.status == "cancelled":
            await update.message.reply_text(
                "â¹ï¸ Ð­ÑÐ° Ð·Ð°Ð¿Ð¸ÑÑ ÑÐ¶Ðµ Ð¾ÑÐ¼ÐµÐ½ÐµÐ½Ð°.",
                reply_markup=main_menu(),
            )
            return

        if booking_item.status == "completed":
            await update.message.reply_text(
                "â ÐÐ°Ð²ÐµÑÑÑÐ½Ð½ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ Ð¾ÑÐ¼ÐµÐ½Ð¸ÑÑ Ð½ÐµÐ»ÑÐ·Ñ.",
                reply_markup=main_menu(),
            )
            return

        booking_item.status = "cancelled"
        db.commit()

        await update.message.reply_text(
            f"â ÐÐ°Ð¿Ð¸ÑÑ #{booking_id} Ð¾ÑÐ¼ÐµÐ½ÐµÐ½Ð°.",
            reply_markup=main_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾ÑÐ¼ÐµÐ½Ð¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ. ÐÐ¾Ð¿ÑÐ¾Ð±ÑÐ¹ÑÐµ Ð¿Ð¾Ð·Ð¶Ðµ.",
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

    # ÐÑÐ¾Ð´Ð¾Ð»Ð¶Ð°ÐµÐ¼ Ð½ÐµÐ·Ð°Ð²ÐµÑÑÑÐ½Ð½Ð¾Ðµ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð¸Ðµ ÑÑÐ»ÑÐ³Ð¸.
    if context.user_data.get("service_creation"):
        handled = await process_service_creation(update, context)
        if handled:
            return

    # ÐÐ°Ð±Ð¸Ð½ÐµÑ Ð¼Ð°ÑÑÐµÑÐ°.
    if text == "ð ÐÐ¾Ð¸ Ð·Ð°Ð¿Ð¸ÑÐ¸":
        await show_master_bookings(update, context)
        return

    if text.startswith("â ÐÐ¾Ð´ÑÐ²ÐµÑÐ´Ð¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð½Ð¾Ð¼ÐµÑ Ð·Ð°Ð¿Ð¸ÑÐ¸.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="confirmed",
        )
        return

    if text.startswith("ð ÐÐ°Ð²ÐµÑÑÐ¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð½Ð¾Ð¼ÐµÑ Ð·Ð°Ð¿Ð¸ÑÐ¸.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="completed",
        )
        return

    if text.startswith("â ÐÑÐ¼ÐµÐ½Ð¸ÑÑ Ð·Ð°ÑÐ²ÐºÑ #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð½Ð¾Ð¼ÐµÑ Ð·Ð°Ð¿Ð¸ÑÐ¸.",
                reply_markup=main_menu(),
            )
            return

        await change_master_booking_status(
            update,
            booking_id,
            new_status="cancelled",
        )
        return

    if text == "â ÐÐ¾Ð±Ð°Ð²Ð¸ÑÑ ÑÑÐ»ÑÐ³Ñ":
        await begin_add_service(update, context)
        return

    if text == "ð ÐÐ¾Ð¸ ÑÑÐ»ÑÐ³Ð¸":
        await show_master_services(update, context)
        return

    if text == "â ÐÑÐºÐ»ÑÑÐ¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ":
        await toggle_master_booking(
            update,
            context,
            enabled=False,
        )
        return

    if text == "â ÐÐºÐ»ÑÑÐ¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ":
        await toggle_master_booking(
            update,
            context,
            enabled=True,
        )
        return

    # ÐÑÐ¼ÐµÐ½Ð° ÐºÐ»Ð¸ÐµÐ½ÑÑÐºÐ¾Ð¹ Ð·Ð°Ð¿Ð¸ÑÐ¸.
    if text.startswith("â ÐÑÐ¼ÐµÐ½Ð¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð½Ð¾Ð¼ÐµÑ Ð·Ð°Ð¿Ð¸ÑÐ¸.",
                reply_markup=main_menu(),
            )
            return

        await cancel_client_booking(update, booking_id)
        return

    # ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ.
    if text == "ð ÐÐ°Ð¿Ð¸ÑÐ°ÑÑÑÑ":
        clear_booking_data(context)
        await booking(update, context)
        return

    if text == "ð¤ ÐÐ¸ÑÐ½ÑÐ¹ ÐºÐ°Ð±Ð¸Ð½ÐµÑ":
        await profile(update, context)
        return

    if text == "ð ÐÐ°Ð¹ÑÐ¸ Ð¼Ð°ÑÑÐµÑÐ°":
        await search(update, context)
        return

    if text == "ð¼ Ð¡ÑÐ°ÑÑ Ð¼Ð°ÑÑÐµÑÐ¾Ð¼":
        await become_master(update, context)
        return

    if text == "â¹ï¸ ÐÐ¾Ð¼Ð¾ÑÑ":
        await update.message.reply_text(
            "â¹ï¸ ÐÐ¾Ð±ÑÐ¾ Ð¿Ð¾Ð¶Ð°Ð»Ð¾Ð²Ð°ÑÑ Ð² BTT!\n\n"
            "ð ÐÐ°Ð¿Ð¸ÑÐ°ÑÑÑÑ â Ð·Ð°Ð¿Ð¸ÑÑ Ðº Ð¼Ð°ÑÑÐµÑÑ\n"
            "ð ÐÐ°Ð¹ÑÐ¸ Ð¼Ð°ÑÑÐµÑÐ° â Ð¿Ð¾Ð¸ÑÐº Ð¿Ð¾ ÐºÐ°ÑÐ°Ð»Ð¾Ð³Ñ\n"
            "ð¤ ÐÐ¸ÑÐ½ÑÐ¹ ÐºÐ°Ð±Ð¸Ð½ÐµÑ â Ð²Ð°ÑÐ¸ Ð·Ð°Ð¿Ð¸ÑÐ¸\n"
            "ð¼ Ð¡ÑÐ°ÑÑ Ð¼Ð°ÑÑÐµÑÐ¾Ð¼ â ÐºÐ°Ð±Ð¸Ð½ÐµÑ Ð¼Ð°ÑÑÐµÑÐ°\n"
            "âï¸ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ â Ð½Ð°ÑÑÑÐ¾Ð¹ÐºÐ¸ Ð°ÐºÐºÐ°ÑÐ½ÑÐ°",
            reply_markup=main_menu(),
        )
        return

    if text == "âï¸ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸":
        await update.message.reply_text(
            "âï¸ ÐÐ°ÑÑÑÐ¾Ð¹ÐºÐ¸ Ð¿Ð¾ÑÐ²ÑÑÑÑ Ð² ÑÐ»ÐµÐ´ÑÑÑÐµÐ¼ ÑÑÐ°Ð¿Ðµ.",
            reply_markup=main_menu(),
        )
        return

    # Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ Ð·Ð°Ð¿Ð¸ÑÐ¸ ÐºÐ»Ð¸ÐµÐ½ÑÐ°.
    if text in CITY_BUTTONS:
        context.user_data["city"] = CITY_BUTTONS[text]

        await update.message.reply_text(
            f"â ÐÐ¾ÑÐ¾Ð´: {CITY_BUTTONS[text]}\n\n"
            "ð Ð¢ÐµÐ¿ÐµÑÑ Ð²ÑÐ±ÐµÑÐ¸ÑÐµ ÐºÐ°ÑÐµÐ³Ð¾ÑÐ¸Ñ.",
            reply_markup=category_menu(),
        )
        return

    if text in CATEGORY_BUTTONS:
        context.user_data["category"] = CATEGORY_BUTTONS[text]

        await update.message.reply_text(
            "ð¤ ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð¼Ð°ÑÑÐµÑÐ°.",
            reply_markup=master_menu(),
        )
        return

    if text.startswith("ð¤") and "#" in text:
        try:
            master_id = int(text.split("#", 1)[1].split()[0])
            master_name = (
                text.split("Â·", 1)[0]
                .replace("ð¤", "")
                .strip()
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð¼Ð°ÑÑÐµÑÐ°. ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð¼Ð°ÑÑÐµÑÐ° ÐºÐ½Ð¾Ð¿ÐºÐ¾Ð¹."
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
            await update.message.reply_text(
                "Ð£ ÑÑÐ¾Ð³Ð¾ Ð¼Ð°ÑÑÐµÑÐ° Ð¿Ð¾ÐºÐ° Ð½ÐµÑ Ð´Ð¾Ð±Ð°Ð²Ð»ÐµÐ½Ð½ÑÑ ÑÑÐ»ÑÐ³.",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return

        context.user_data["master_id"] = master_id
        context.user_data["master_name"] = master_name
        context.user_data.pop("service_id", None)
        context.user_data.pop("service_title", None)

        await update.message.reply_text(
            f"â ÐÐ°ÑÑÐµÑ: {master_name}\n\n"
            "ð¼ Ð¢ÐµÐ¿ÐµÑÑ Ð²ÑÐ±ÐµÑÐ¸ÑÐµ ÑÑÐ»ÑÐ³Ñ:",
            reply_markup=service_menu(services),
        )
        return

    if text.startswith("ð¼") and "#" in text:
        try:
            service_id = int(text.split("#", 1)[1].split()[0])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ ÑÑÐ»ÑÐ³Ñ. ÐÑÐ±ÐµÑÐ¸ÑÐµ ÐµÑ ÐºÐ½Ð¾Ð¿ÐºÐ¾Ð¹."
            )
            return

        master_id = context.user_data.get("master_id")

        if master_id is None:
            await update.message.reply_text(
                "Ð¡Ð½Ð°ÑÐ°Ð»Ð° Ð²ÑÐ±ÐµÑÐ¸ÑÐµ Ð¼Ð°ÑÑÐµÑÐ°.",
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
            await update.message.reply_text(
                "Ð£ÑÐ»ÑÐ³Ð° Ð½Ðµ Ð½Ð°Ð¹Ð´ÐµÐ½Ð° Ð¸Ð»Ð¸ Ð½Ðµ Ð¿ÑÐ¸Ð½Ð°Ð´Ð»ÐµÐ¶Ð¸Ñ Ð²ÑÐ±ÑÐ°Ð½Ð½Ð¾Ð¼Ñ Ð¼Ð°ÑÑÐµÑÑ.",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return

        context.user_data["service_id"] = service.id
        context.user_data["service_title"] = service.title

        await update.message.reply_text(
            f"â Ð£ÑÐ»ÑÐ³Ð°: {service.title}\n"
            f"â± ÐÐ»Ð¸ÑÐµÐ»ÑÐ½Ð¾ÑÑÑ: {service.duration} Ð¼Ð¸Ð½.\n"
            f"ð° Ð¦ÐµÐ½Ð°: {service.price}\n\n"
            "ð ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð´Ð°ÑÑ.",
            reply_markup=date_menu(),
        )
        return

    if text == "Ð£ÑÐ»ÑÐ³ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ":
        await update.message.reply_text(
            "Ð£ Ð²ÑÐ±ÑÐ°Ð½Ð½Ð¾Ð³Ð¾ Ð¼Ð°ÑÑÐµÑÐ° Ð¿Ð¾ÐºÐ° Ð½ÐµÑ Ð´Ð¾ÑÑÑÐ¿Ð½ÑÑ ÑÑÐ»ÑÐ³.",
            reply_markup=main_menu(),
        )
        clear_booking_data(context)
        return

    if text == "Ð¡Ð²Ð¾Ð±Ð¾Ð´Ð½Ð¾Ð³Ð¾ Ð²ÑÐµÐ¼ÐµÐ½Ð¸ Ð½ÐµÑ":
        await update.message.reply_text(
            "ÐÐ° Ð²ÑÐ±ÑÐ°Ð½Ð½ÑÑ Ð´Ð°ÑÑ ÑÐ²Ð¾Ð±Ð¾Ð´Ð½ÑÑ ÑÐ»Ð¾ÑÐ¾Ð² Ð½ÐµÑ. "
            "ÐÑÐ±ÐµÑÐ¸ÑÐµ Ð´ÑÑÐ³ÑÑ Ð´Ð°ÑÑ.",
            reply_markup=date_menu(),
        )
        return

    if text in DATE_BUTTONS:
        selected_date = date.today() + timedelta(
            days=DATE_BUTTONS[text]
        )

        master_id = context.user_data.get("master_id")
        service_id = context.user_data.get("service_id")

        if master_id is None or service_id is None:
            clear_booking_data(context)

            await update.message.reply_text(
                "â ï¸ Ð¡Ð½Ð°ÑÐ°Ð»Ð° Ð²ÑÐ±ÐµÑÐ¸ÑÐµ Ð¼Ð°ÑÑÐµÑÐ° Ð¸ ÑÑÐ»ÑÐ³Ñ.",
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
            await update.message.reply_text(
                f"â ï¸ {error}",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return
        except Exception:
            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð·Ð°Ð³ÑÑÐ·Ð¸ÑÑ ÑÐ²Ð¾Ð±Ð¾Ð´Ð½Ð¾Ðµ Ð²ÑÐµÐ¼Ñ.",
                reply_markup=main_menu(),
            )
            clear_booking_data(context)
            return
        finally:
            db.close()

        context.user_data["booking_date"] = selected_date

        await update.message.reply_text(
            f"â ÐÐ°ÑÐ°: {selected_date.strftime('%d.%m.%Y')}\n\n"
            "ð ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÐ²Ð¾Ð±Ð¾Ð´Ð½Ð¾Ðµ Ð²ÑÐµÐ¼Ñ.",
            reply_markup=available_time_menu(slots),
        )
        return

    if text.startswith("ð "):
        try:
            selected_time = datetime.strptime(
                text.replace("ð ", "", 1),
                "%H:%M",
            ).time()
        except ValueError:
            await update.message.reply_text(
                "ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ Ð¾Ð¿ÑÐµÐ´ÐµÐ»Ð¸ÑÑ Ð²ÑÐµÐ¼Ñ. ÐÑÐ±ÐµÑÐ¸ÑÐµ ÑÐ»Ð¾Ñ ÐºÐ½Ð¾Ð¿ÐºÐ¾Ð¹."
            )
            return

        context.user_data["booking_time"] = selected_time

        booking_date = context.user_data.get("booking_date")
        date_text = (
            booking_date.strftime("%d.%m.%Y")
            if booking_date
            else "â"
        )

        await update.message.reply_text(
            "ð ÐÐ¾Ð´ÑÐ²ÐµÑÐ¶Ð´ÐµÐ½Ð¸Ðµ Ð·Ð°Ð¿Ð¸ÑÐ¸\n\n"
            f"ð ÐÐ¾ÑÐ¾Ð´: {context.user_data.get('city', 'â')}\n"
            f"ð ÐÐ°ÑÐµÐ³Ð¾ÑÐ¸Ñ: {context.user_data.get('category', 'â')}\n"
            f"ð¤ ÐÐ°ÑÑÐµÑ: {context.user_data.get('master_name', 'â')}\n"
            f"ð¼ Ð£ÑÐ»ÑÐ³Ð°: {context.user_data.get('service_title', 'â')}\n"
            f"ð ÐÐ°ÑÐ°: {date_text}\n"
            f"ð ÐÑÐµÐ¼Ñ: {selected_time.strftime('%H:%M')}\n\n"
            "ÐÐ¾Ð´ÑÐ²ÐµÑÐ´Ð¸ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ?",
            reply_markup=confirm_menu(),
        )
        return

    if text == "â ÐÐ¾Ð´ÑÐ²ÐµÑÐ´Ð¸ÑÑ":
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
                "â ï¸ ÐÐ°Ð½Ð½ÑÐµ Ð·Ð°Ð¿Ð¸ÑÐ¸ Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ñ Ð½Ðµ Ð¿Ð¾Ð»Ð½Ð¾ÑÑÑÑ. ÐÐ°ÑÐ½Ð¸ÑÐµ Ð·Ð°Ð½Ð¾Ð²Ð¾.",
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
                f"â ï¸ {error}",
                reply_markup=main_menu(),
            )
            return
        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "â ÐÐµ ÑÐ´Ð°Ð»Ð¾ÑÑ ÑÐ¾Ð·Ð´Ð°ÑÑ Ð·Ð°Ð¿Ð¸ÑÑ. ÐÐ¾Ð¿ÑÐ¾Ð±ÑÐ¹ÑÐµ ÐµÑÑ ÑÐ°Ð·.",
                reply_markup=main_menu(),
            )
            return

        clear_booking_data(context)

        await update.message.reply_text(
            "ð ÐÐ°Ð¿Ð¸ÑÑ ÑÑÐ¿ÐµÑÐ½Ð¾ ÑÐ¾Ð·Ð´Ð°Ð½Ð°!\n\n"
            f"ÐÐ¾Ð¼ÐµÑ Ð·Ð°Ð¿Ð¸ÑÐ¸: {created_booking.id}",
            reply_markup=main_menu(),
        )
        return

    if text == "â ÐÑÐ¼ÐµÐ½Ð¸ÑÑ":
        clear_booking_data(context)

        await update.message.reply_text(
            "â Ð¡Ð¾Ð·Ð´Ð°Ð½Ð¸Ðµ Ð·Ð°Ð¿Ð¸ÑÐ¸ Ð¾ÑÐ¼ÐµÐ½ÐµÐ½Ð¾.",
            reply_markup=main_menu(),
        )
        return

    if text == "â¬ï¸ ÐÐ°Ð·Ð°Ð´":
        clear_booking_data(context)

        await update.message.reply_text(
            "ð  ÐÐ»Ð°Ð²Ð½Ð¾Ðµ Ð¼ÐµÐ½Ñ",
            reply_markup=main_menu(),
        )
        return

    if text == "ÐÐ°ÑÑÐµÑÐ¾Ð² Ð¿Ð¾ÐºÐ° Ð½ÐµÑ":
        await update.message.reply_text(
            "Ð ÑÐ¸ÑÑÐµÐ¼Ðµ Ð¿Ð¾ÐºÐ° Ð½ÐµÑ Ð´Ð¾ÑÑÑÐ¿Ð½ÑÑ Ð¼Ð°ÑÑÐµÑÐ¾Ð².",
            reply_markup=main_menu(),
        )
        return

    await update.message.reply_text(
        "ÐÐ¾Ð¶Ð°Ð»ÑÐ¹ÑÑÐ°, Ð¸ÑÐ¿Ð¾Ð»ÑÐ·ÑÐ¹ÑÐµ ÐºÐ½Ð¾Ð¿ÐºÐ¸ Ð¼ÐµÐ½Ñ.",
        reply_markup=main_menu(),
    )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)
