import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram.ext import Application

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master


logger = logging.getLogger(__name__)


def _booking_datetime(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
    )


async def _send_reminder(
    application: Application,
    booking: Booking,
    reminder_title: str,
) -> bool:
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

    delivered = False

    if client is not None:
        try:
            await application.bot.send_message(
                chat_id=client.telegram_id,
                text=(
                    f"⏰ {reminder_title}\n\n"
                    f"Запись #{booking.id}\n"
                    f"Услуга: {service_title}\n"
                    f"Мастер: {master_name}\n"
                    f"Дата: {date_text}\n"
                    f"Время: {time_text}"
                ),
            )
            delivered = True
        except Exception:
            logger.exception(
                "Не удалось отправить напоминание клиенту "
                "по записи %s",
                booking.id,
            )

    if master_user is not None:
        try:
            await application.bot.send_message(
                chat_id=master_user.telegram_id,
                text=(
                    f"⏰ {reminder_title}\n\n"
                    f"Запись #{booking.id}\n"
                    f"Клиент: {client_name}\n"
                    f"Услуга: {service_title}\n"
                    f"Дата: {date_text}\n"
                    f"Время: {time_text}"
                ),
            )
            delivered = True
        except Exception:
            logger.exception(
                "Не удалось отправить напоминание мастеру "
                "по записи %s",
                booking.id,
            )

    return delivered


async def process_booking_reminders(
    application: Application,
) -> None:
    """
    Проверяет подтверждённые записи и отправляет напоминания.

    Функцию безопасно запускать каждые 5–10 минут.
    """
    db = SessionLocal()

    try:
        now = datetime.now()
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

            # Напоминание за 24 часа:
            # отправляется в окне от 23 до 25 часов до записи.
            if (
                not booking.reminder_24h_sent
                and timedelta(hours=23)
                <= time_left
                <= timedelta(hours=25)
            ):
                delivered = await _send_reminder(
                    application,
                    booking,
                    "Напоминание: запись примерно через 24 часа",
                )

                if delivered:
                    booking.reminder_24h_sent = True
                    db.commit()

            # Напоминание за 2 часа:
            # отправляется в окне от 1 ч 30 мин до 2 ч 30 мин.
            if (
                not booking.reminder_2h_sent
                and timedelta(minutes=90)
                <= time_left
                <= timedelta(minutes=150)
            ):
                delivered = await _send_reminder(
                    application,
                    booking,
                    "Напоминание: запись примерно через 2 часа",
                )

                if delivered:
                    booking.reminder_2h_sent = True
                    db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "Ошибка при обработке напоминаний о записях"
        )

    finally:
        db.close()
