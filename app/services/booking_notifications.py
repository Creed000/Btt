import logging

from telegram.ext import Application

from app.models.booking import Booking


logger = logging.getLogger(__name__)


def _notifications_allowed(
    user,
) -> bool:
    if user is None:
        return False

    return bool(
        getattr(
            user,
            "notifications_enabled",
            True,
        )
    )


async def notify_master_about_new_booking(
    application: Application,
    booking: Booking,
) -> bool:
    master_user = (
        booking.master.user
        if booking.master and booking.master.user
        else None
    )

    if master_user is None:
        logger.warning(
            "У записи %s отсутствует пользователь мастера",
            booking.id,
        )
        return False

    if not _notifications_allowed(master_user):
        logger.info(
            "Уведомление мастеру пропущено по настройкам. "
            "Запись: %s",
            booking.id,
        )
        return False

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=(
                "🔔 Новая запись!\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: "
                f"{booking.service.title if booking.service else '—'}\n"
                f"Дата: "
                f"{booking.booking_date.strftime('%d.%m.%Y')}\n"
                f"Время: "
                f"{booking.booking_time.strftime('%H:%M')}\n"
                f"Клиент: "
                f"{booking.client.first_name if booking.client else '—'}"
            ),
        )
        return True

    except Exception:
        logger.exception(
            "Не удалось отправить уведомление мастеру "
            "по записи %s",
            booking.id,
        )
        return False


async def notify_client_about_status(
    application: Application,
    booking: Booking,
) -> bool:
    client = booking.client

    if client is None:
        logger.warning(
            "У записи %s отсутствует клиент",
            booking.id,
        )
        return False

    if not _notifications_allowed(client):
        logger.info(
            "Уведомление клиенту пропущено по настройкам. "
            "Запись: %s",
            booking.id,
        )
        return False

    status_messages = {
        "confirmed": "✅ Ваша запись подтверждена.",
        "completed": "🏁 Ваша запись завершена.",
        "cancelled": "❌ Ваша запись отменена.",
    }

    status_text = status_messages.get(
        booking.status
    )

    if status_text is None:
        return False

    master_name = "—"

    if (
        booking.master is not None
        and booking.master.user is not None
    ):
        master_name = (
            booking.master.user.first_name
            or "Мастер"
        )

    try:
        await application.bot.send_message(
            chat_id=client.telegram_id,
            text=(
                f"{status_text}\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: "
                f"{booking.service.title if booking.service else '—'}\n"
                f"Дата: "
                f"{booking.booking_date.strftime('%d.%m.%Y')}\n"
                f"Время: "
                f"{booking.booking_time.strftime('%H:%M')}\n"
                f"Мастер: {master_name}"
            ),
        )
        return True

    except Exception:
        logger.exception(
            "Не удалось отправить уведомление клиенту "
            "по записи %s",
            booking.id,
        )
        return False


async def notify_master_about_client_cancellation(
    application: Application,
    booking: Booking,
) -> bool:
    master_user = (
        booking.master.user
        if booking.master and booking.master.user
        else None
    )

    if master_user is None:
        logger.warning(
            "У записи %s отсутствует пользователь мастера",
            booking.id,
        )
        return False

    if not _notifications_allowed(master_user):
        logger.info(
            "Уведомление мастеру об отмене пропущено "
            "по настройкам. Запись: %s",
            booking.id,
        )
        return False

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=(
                "⚠️ Клиент отменил запись.\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: "
                f"{booking.service.title if booking.service else '—'}\n"
                f"Дата: "
                f"{booking.booking_date.strftime('%d.%m.%Y')}\n"
                f"Время: "
                f"{booking.booking_time.strftime('%H:%M')}\n"
                f"Клиент: "
                f"{booking.client.first_name if booking.client else '—'}"
            ),
        )
        return True

    except Exception:
        logger.exception(
            "Не удалось уведомить мастера об отмене записи %s",
            booking.id,
        )
        return False
