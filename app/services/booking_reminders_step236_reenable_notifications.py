import logging
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram.ext import Application

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)


class ReminderDeliveryResult(str, Enum):
    SENT = "sent"
    DISABLED = "disabled"
    FAILED = "failed"
    NO_RECIPIENT = "no_recipient"


def _booking_datetime(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
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


def _reminder_texts(
    booking: Booking,
    reminder_title: str,
) -> tuple[str, str]:
    client = booking.client
    master_user = (
        booking.master.user
        if booking.master and booking.master.user
        else None
    )

    service_title = (
        booking.service.title
        if booking.service
        else "Услуга"
    )

    master_name = (
        master_user.first_name
        if master_user and master_user.first_name
        else "Мастер"
    )

    client_name = (
        client.first_name
        if client and client.first_name
        else "Клиент"
    )

    date_text = booking.booking_date.strftime(
        "%d.%m.%Y"
    )
    time_text = booking.booking_time.strftime(
        "%H:%M"
    )

    client_text = (
        f"⏰ {reminder_title}\n\n"
        f"Запись #{booking.id}\n"
        f"Услуга: {service_title}\n"
        f"Мастер: {master_name}\n"
        f"Дата: {date_text}\n"
        f"Время: {time_text}"
    )

    master_text = (
        f"⏰ {reminder_title}\n\n"
        f"Запись #{booking.id}\n"
        f"Клиент: {client_name}\n"
        f"Услуга: {service_title}\n"
        f"Дата: {date_text}\n"
        f"Время: {time_text}"
    )

    return client_text, master_text


async def _send_to_client(
    application: Application,
    booking: Booking,
    text: str,
) -> ReminderDeliveryResult:
    client = booking.client

    if client is None:
        return ReminderDeliveryResult.NO_RECIPIENT

    if not _notifications_allowed(client):
        return ReminderDeliveryResult.DISABLED

    try:
        await application.bot.send_message(
            chat_id=client.telegram_id,
            text=text,
        )
        return ReminderDeliveryResult.SENT

    except Exception:
        logger.exception(
            "Не удалось отправить напоминание клиенту "
            "по записи %s",
            booking.id,
        )
        return ReminderDeliveryResult.FAILED


async def _send_to_master(
    application: Application,
    booking: Booking,
    text: str,
) -> ReminderDeliveryResult:
    master_user = (
        booking.master.user
        if booking.master and booking.master.user
        else None
    )

    if master_user is None:
        return ReminderDeliveryResult.NO_RECIPIENT

    if not _notifications_allowed(master_user):
        return ReminderDeliveryResult.DISABLED

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=text,
        )
        return ReminderDeliveryResult.SENT

    except Exception:
        logger.exception(
            "Не удалось отправить напоминание мастеру "
            "по записи %s",
            booking.id,
        )
        return ReminderDeliveryResult.FAILED


def _result_counts_as_finished(
    result: ReminderDeliveryResult,
) -> bool:
    return result in {
        ReminderDeliveryResult.SENT,
        ReminderDeliveryResult.NO_RECIPIENT,
    }


async def _process_reminder_period(
    application: Application,
    booking: Booking,
    reminder_title: str,
    common_flag_name: str,
    client_flag_name: str,
    master_flag_name: str,
) -> bool:
    """
    Возвращает True, если состояние записи изменилось.

    Отключённые уведомления не помечаются доставленными.
    Поэтому после повторного включения пользователь сможет
    получить ещё актуальное напоминание.
    """
    changed = False

    if getattr(booking, common_flag_name):
        if not getattr(booking, client_flag_name):
            setattr(booking, client_flag_name, True)
            changed = True

        if not getattr(booking, master_flag_name):
            setattr(booking, master_flag_name, True)
            changed = True

        return changed

    client_text, master_text = _reminder_texts(
        booking,
        reminder_title,
    )

    if not getattr(booking, client_flag_name):
        client_result = await _send_to_client(
            application,
            booking,
            client_text,
        )

        if _result_counts_as_finished(
            client_result
        ):
            setattr(
                booking,
                client_flag_name,
                True,
            )
            changed = True

    if not getattr(booking, master_flag_name):
        master_result = await _send_to_master(
            application,
            booking,
            master_text,
        )

        if _result_counts_as_finished(
            master_result
        ):
            setattr(
                booking,
                master_flag_name,
                True,
            )
            changed = True

    all_finished = (
        getattr(booking, client_flag_name)
        and getattr(booking, master_flag_name)
    )

    if (
        all_finished
        and not getattr(
            booking,
            common_flag_name,
        )
    ):
        setattr(
            booking,
            common_flag_name,
            True,
        )
        changed = True

    return changed


async def process_booking_reminders(
    application: Application,
) -> None:
    """
    Проверяет подтверждённые записи и отправляет напоминания.
    """
    db = SessionLocal()

    try:
        now = local_naive_now()
        search_until = now + timedelta(
            hours=25,
        )

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.client),
                    joinedload(Booking.service),
                    joinedload(Booking.master).joinedload(
                        Master.user
                    ),
                )
                .where(
                    Booking.status == "confirmed",
                    Booking.booking_date >= now.date(),
                    Booking.booking_date <= search_until.date(),
                )
                .order_by(
                    Booking.booking_date,
                    Booking.booking_time,
                )
            ).unique().all()
        )

        for booking in bookings:
            starts_at = _booking_datetime(
                booking
            )
            time_left = starts_at - now

            if time_left.total_seconds() <= 0:
                continue

            changed = False

            if time_left <= timedelta(hours=2):
                changed = (
                    await _process_reminder_period(
                        application=application,
                        booking=booking,
                        reminder_title=(
                            "Напоминание: запись менее чем через 2 часа"
                        ),
                        common_flag_name="reminder_2h_sent",
                        client_flag_name="reminder_2h_client_sent",
                        master_flag_name="reminder_2h_master_sent",
                    )
                    or changed
                )

            elif time_left <= timedelta(hours=24):
                changed = (
                    await _process_reminder_period(
                        application=application,
                        booking=booking,
                        reminder_title=(
                            "Напоминание: запись в течение ближайших 24 часов"
                        ),
                        common_flag_name="reminder_24h_sent",
                        client_flag_name="reminder_24h_client_sent",
                        master_flag_name="reminder_24h_master_sent",
                    )
                    or changed
                )

            if changed:
                db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при обработке напоминаний о записях"
        )

    finally:
        db.close()
