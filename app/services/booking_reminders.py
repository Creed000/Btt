import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram.ext import Application

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.services.booking_time_display import (
    format_booking_time_for_user,
)
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)


def _booking_datetime(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
    )


def _notifications_enabled(user) -> bool:
    if user is None:
        return False

    if not getattr(user, "is_active", True):
        return False

    return bool(
        getattr(
            user,
            "notifications_enabled",
            True,
        )
    )


def _client_text(
    booking: Booking,
    title: str,
) -> str:
    client = booking.client

    master_user = (
        booking.master.user
        if booking.master
        and booking.master.user
        else None
    )

    master_name = (
        master_user.first_name
        if master_user
        and master_user.first_name
        else "Мастер"
    )

    service_title = (
        booking.service.title
        if booking.service
        else "Услуга"
    )

    time_text = format_booking_time_for_user(
        booking_date=booking.booking_date,
        booking_time=booking.booking_time,
        user=client,
    )

    return (
        f"⏰ {title}\n\n"
        f"Запись #{booking.id}\n"
        f"💼 {service_title}\n"
        f"👤 Мастер: {master_name}\n"
        f"🕒 {time_text}"
    )


def _master_text(
    booking: Booking,
    title: str,
) -> str:
    master_user = (
        booking.master.user
        if booking.master
        and booking.master.user
        else None
    )

    client = booking.client

    client_name = (
        client.first_name
        if client
        and client.first_name
        else "Клиент"
    )

    service_title = (
        booking.service.title
        if booking.service
        else "Услуга"
    )

    time_text = format_booking_time_for_user(
        booking_date=booking.booking_date,
        booking_time=booking.booking_time,
        user=master_user,
    )

    return (
        f"⏰ {title}\n\n"
        f"Запись #{booking.id}\n"
        f"👤 Клиент: {client_name}\n"
        f"💼 {service_title}\n"
        f"🕒 {time_text}"
    )


async def _send_to_client(
    application: Application,
    booking: Booking,
    title: str,
) -> bool:
    client = booking.client

    if not _notifications_enabled(client):
        return False

    try:
        await application.bot.send_message(
            chat_id=client.telegram_id,
            text=_client_text(
                booking,
                title,
            ),
        )
        return True

    except Exception:
        logger.exception(
            "Не удалось отправить напоминание "
            "клиенту по записи %s",
            booking.id,
        )
        return False


async def _send_to_master(
    application: Application,
    booking: Booking,
    title: str,
) -> bool:
    master_user = (
        booking.master.user
        if booking.master
        and booking.master.user
        else None
    )

    if not _notifications_enabled(
        master_user
    ):
        return False

    try:
        await application.bot.send_message(
            chat_id=master_user.telegram_id,
            text=_master_text(
                booking,
                title,
            ),
        )
        return True

    except Exception:
        logger.exception(
            "Не удалось отправить напоминание "
            "мастеру по записи %s",
            booking.id,
        )
        return False


async def _still_confirmed(
    booking_id: int,
) -> bool:
    db = SessionLocal()

    try:
        status = db.scalar(
            select(Booking.status).where(
                Booking.id == booking_id
            )
        )

        return status == "confirmed"

    finally:
        db.close()


async def _process_stage(
    application: Application,
    db,
    booking: Booking,
    *,
    stage: str,
    title: str,
) -> None:
    if stage == "24h":
        client_field = (
            "reminder_24h_client_sent"
        )
        master_field = (
            "reminder_24h_master_sent"
        )
        legacy_field = "reminder_24h_sent"
    else:
        client_field = (
            "reminder_2h_client_sent"
        )
        master_field = (
            "reminder_2h_master_sent"
        )
        legacy_field = "reminder_2h_sent"

    client_sent = bool(
        getattr(
            booking,
            client_field,
            False,
        )
    )
    master_sent = bool(
        getattr(
            booking,
            master_field,
            False,
        )
    )

    if not client_sent:
        if not await _still_confirmed(
            booking.id
        ):
            return

        if await _send_to_client(
            application,
            booking,
            title,
        ):
            setattr(
                booking,
                client_field,
                True,
            )
            client_sent = True
            db.commit()

    if not master_sent:
        if not await _still_confirmed(
            booking.id
        ):
            return

        if await _send_to_master(
            application,
            booking,
            title,
        ):
            setattr(
                booking,
                master_field,
                True,
            )
            master_sent = True
            db.commit()

    # Старый общий флаг ставим только когда оба
    # новых получателя реально получили сообщение.
    if (
        client_sent
        and master_sent
        and not getattr(
            booking,
            legacy_field,
            False,
        )
    ):
        setattr(
            booking,
            legacy_field,
            True,
        )
        db.commit()


async def process_booking_reminders(
    application: Application,
) -> None:
    """
    Запускается фоновым job примерно каждые 5 минут.

    24h-напоминание:
      когда до записи <= 24 часов, но > 2 часов.

    2h-напоминание:
      когда до записи <= 2 часов, но запись ещё не началась.

    Такая схема переживает рестарт Railway и пропущенный
    точный временной интервал.
    """
    db = SessionLocal()

    try:
        now = local_naive_now()
        search_until = (
            now + timedelta(hours=24)
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
                    Booking.status
                    == "confirmed",
                    Booking.booking_date
                    >= now.date(),
                    Booking.booking_date
                    <= search_until.date(),
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

            if time_left <= timedelta(0):
                continue

            if time_left <= timedelta(
                hours=2
            ):
                await _process_stage(
                    application,
                    db,
                    booking,
                    stage="2h",
                    title=(
                        "Напоминание: запись "
                        "примерно через 2 часа"
                    ),
                )

            elif time_left <= timedelta(
                hours=24
            ):
                await _process_stage(
                    application,
                    db,
                    booking,
                    stage="24h",
                    title=(
                        "Напоминание: запись "
                        "примерно через 24 часа"
                    ),
                )

    except Exception:
        db.rollback()

        logger.exception(
            "Ошибка при обработке "
            "напоминаний о записях"
        )

    finally:
        db.close()
