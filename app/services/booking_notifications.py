import logging
from datetime import datetime
from enum import Enum

from telegram.ext import Application

from app.models.booking import Booking
from app.services.user_timezone import format_datetime_for_user


logger = logging.getLogger(__name__)


class NotificationResult(str, Enum):
    SENT = "sent"
    DISABLED = "disabled"
    FAILED = "failed"



def _booking_datetime(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
    )


def _booking_datetime_text(
    booking: Booking,
    user,
) -> str:
    return format_datetime_for_user(
        _booking_datetime(booking),
        user,
        pattern="%d.%m.%Y %H:%M",
    )

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
) -> NotificationResult:
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
        return NotificationResult.FAILED

    if not _notifications_allowed(master_user):
        logger.info(
            "Уведомление мастеру пропущено по настройкам. "
            "Запись: %s",
            booking.id,
        )
        return NotificationResult.DISABLED

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=(
                "🔔 Новая запись!\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: "
                f"{booking.service.title if booking.service else '—'}\n"
                f"Дата и время: "
                f"{_booking_datetime_text(booking, master_user)}\n"
                f"Клиент: "
                f"{booking.client.first_name if booking.client else '—'}"
            ),
        )
        return NotificationResult.SENT

    except Exception:
        logger.exception(
            "Не удалось отправить уведомление мастеру "
            "по записи %s",
            booking.id,
        )
        return NotificationResult.FAILED


async def notify_client_about_status(
    application: Application,
    booking: Booking,
) -> NotificationResult:
    client = booking.client

    if client is None:
        logger.warning(
            "У записи %s отсутствует клиент",
            booking.id,
        )
        return NotificationResult.FAILED

    if not _notifications_allowed(client):
        logger.info(
            "Уведомление клиенту пропущено по настройкам. "
            "Запись: %s",
            booking.id,
        )
        return NotificationResult.DISABLED

    status_messages = {
        "confirmed": "✅ Ваша запись подтверждена.",
        "completed": "🏁 Ваша запись завершена.",
        "cancelled": "❌ Ваша запись отменена.",
    }

    status_text = status_messages.get(
        booking.status
    )

    if status_text is None:
        return NotificationResult.FAILED

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
                f"Дата и время: "
                f"{_booking_datetime_text(booking, master_user)}\n"
                f"Мастер: {master_name}"
            ),
        )
        return NotificationResult.SENT

    except Exception:
        logger.exception(
            "Не удалось отправить уведомление клиенту "
            "по записи %s",
            booking.id,
        )
        return NotificationResult.FAILED


async def notify_master_about_client_cancellation(
    application: Application,
    booking: Booking,
) -> NotificationResult:
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
        return NotificationResult.FAILED

    if not _notifications_allowed(master_user):
        logger.info(
            "Уведомление мастеру об отмене пропущено "
            "по настройкам. Запись: %s",
            booking.id,
        )
        return NotificationResult.DISABLED

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=(
                "⚠️ Клиент отменил запись.\n\n"
                f"Номер: #{booking.id}\n"
                f"Услуга: "
                f"{booking.service.title if booking.service else '—'}\n"
                f"Дата и время: "
                f"{_booking_datetime_text(booking, master_user)}\n"
                f"Клиент: "
                f"{booking.client.first_name if booking.client else '—'}"
            ),
        )
        return NotificationResult.SENT

    except Exception:
        logger.exception(
            "Не удалось уведомить мастера об отмене записи %s",
            booking.id,
        )
        return NotificationResult.FAILED


def notification_result_text(
    result: NotificationResult,
    recipient_name: str,
) -> str:
    if result == NotificationResult.SENT:
        return f"{recipient_name} получил уведомление."

    if result == NotificationResult.DISABLED:
        return (
            f"У {recipient_name.lower()} уведомления выключены "
            "в настройках."
        )

    return (
        f"Уведомление для {recipient_name.lower()} "
        "доставить не удалось."
    )
