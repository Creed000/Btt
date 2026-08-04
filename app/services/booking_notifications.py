import logging

from telegram.ext import Application

from app.models.booking import Booking


logger = logging.getLogger(__name__)


async def notify_master_about_new_booking(
    application: Application,
    booking: Booking,
) -> None:
    master_user = (
        booking.master.user
        if booking.master and booking.master.user
        else None
    )

    if master_user is None:
        return

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=(
                "🔔 Новая запись!\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: {booking.service.title if booking.service else '—'}\n"
                f"Дата: {booking.booking_date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.booking_time.strftime('%H:%M')}\n"
                f"Клиент: "
                f"{booking.client.first_name if booking.client else '—'}"
            ),
        )
    except Exception:
        logger.exception(
            "Не удалось отправить уведомление мастеру по записи %s",
            booking.id,
        )


async def notify_client_about_status(
    application: Application,
    booking: Booking,
) -> None:
    if booking.client is None:
        return

    status_messages = {
        "confirmed": "✅ Ваша запись подтверждена.",
        "completed": "🏁 Ваша запись завершена.",
        "cancelled": "❌ Ваша запись отменена.",
    }

    status_text = status_messages.get(booking.status)

    if status_text is None:
        return

    try:
        await application.bot.send_message(
            chat_id=booking.client.telegram_id,
            text=(
                f"{status_text}\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: {booking.service.title if booking.service else '—'}\n"
                f"Дата: {booking.booking_date.strftime('%d.%m.%Y')}\n"
                f"Время: {booking.booking_time.strftime('%H:%M')}\n"
                f"Мастер: "
                f"{booking.master.user.first_name if booking.master and booking.master.user else '—'}"
            ),
        )
    except Exception:
        logger.exception(
            "Не удалось отправить уведомление клиенту по записи %s",
            booking.id,
        )
