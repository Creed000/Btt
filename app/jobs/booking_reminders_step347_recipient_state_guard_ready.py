import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload
from telegram.ext import Application

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.services.timezone import local_naive_now


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderPayload:
    booking_id: int
    reminder_kind: str
    client_telegram_id: int | None
    master_telegram_id: int | None
    client_notifications_enabled: bool
    master_notifications_enabled: bool
    client_sent: bool
    master_sent: bool
    client_name: str
    master_name: str
    service_title: str
    date_text: str
    time_text: str


def _booking_datetime(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
    )


def _notifications_enabled(
    user,
) -> bool:
    if user is None:
        return False

    # Совместимость со старой БД до upgrade:
    # если поля ещё нет, уведомления считаем включёнными.
    return bool(
        getattr(
            user,
            "notifications_enabled",
            True,
        )
    )


def _flag_value(
    booking: Booking,
    name: str,
) -> bool:
    return bool(
        getattr(
            booking,
            name,
            False,
        )
    )


def _build_payload(
    booking: Booking,
    reminder_kind: str,
) -> ReminderPayload:
    client = booking.client
    master_user = (
        booking.master.user
        if booking.master
        and booking.master.user
        else None
    )

    prefix = (
        "reminder_24h"
        if reminder_kind == "24h"
        else "reminder_2h"
    )

    return ReminderPayload(
        booking_id=booking.id,
        reminder_kind=reminder_kind,
        client_telegram_id=(
            client.telegram_id
            if client is not None
            else None
        ),
        master_telegram_id=(
            master_user.telegram_id
            if master_user is not None
            else None
        ),
        client_notifications_enabled=(
            _notifications_enabled(client)
        ),
        master_notifications_enabled=(
            _notifications_enabled(master_user)
        ),
        client_sent=_flag_value(
            booking,
            f"{prefix}_client_sent",
        ),
        master_sent=_flag_value(
            booking,
            f"{prefix}_master_sent",
        ),
        client_name=(
            client.first_name
            if client is not None
            and client.first_name
            else "Клиент"
        ),
        master_name=(
            master_user.first_name
            if master_user is not None
            and master_user.first_name
            else "Мастер"
        ),
        service_title=(
            booking.service.title
            if booking.service is not None
            else "Услуга"
        ),
        date_text=booking.booking_date.strftime(
            "%d.%m.%Y"
        ),
        time_text=booking.booking_time.strftime(
            "%H:%M"
        ),
    )


def _load_due_reminders() -> list[ReminderPayload]:
    """
    Только синхронная работа с SQLAlchemy.
    Вызывается через asyncio.to_thread().
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
                    joinedload(
                        Booking.master
                    ).joinedload(
                        Master.user
                    ),
                )
                .where(
                    Booking.status == "confirmed",
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

        payloads: list[
            ReminderPayload
        ] = []

        for booking in bookings:
            starts_at = _booking_datetime(
                booking
            )
            time_left = (
                starts_at - now
            )

            if (
                time_left.total_seconds()
                <= 0
            ):
                continue

            if (
                timedelta(hours=23)
                <= time_left
                <= timedelta(hours=25)
            ):
                payload = _build_payload(
                    booking,
                    "24h",
                )

                if (
                    not payload.client_sent
                    or not payload.master_sent
                ):
                    payloads.append(
                        payload
                    )

            if (
                timedelta(minutes=90)
                <= time_left
                <= timedelta(minutes=150)
            ):
                payload = _build_payload(
                    booking,
                    "2h",
                )

                if (
                    not payload.client_sent
                    or not payload.master_sent
                ):
                    payloads.append(
                        payload
                    )

        return payloads

    finally:
        db.close()


CLAIM_TTL = timedelta(minutes=15)


def _field_names(
    reminder_kind: str,
    recipient: str,
) -> tuple[str, str]:
    if reminder_kind not in {"24h", "2h"}:
        raise ValueError("Неизвестный тип напоминания.")

    if recipient not in {"client", "master"}:
        raise ValueError("Неизвестный получатель напоминания.")

    prefix = (
        "reminder_24h"
        if reminder_kind == "24h"
        else "reminder_2h"
    )

    return (
        f"{prefix}_{recipient}_sent",
        f"{prefix}_{recipient}_claimed_at",
    )


def _claim_recipient(
    booking_id: int,
    reminder_kind: str,
    recipient: str,
) -> datetime | None:
    """
    Атомарно забирает право на отправку одному получателю.

    Возвращает claim timestamp, если именно этот worker
    получил право отправлять сообщение.
    """
    db = SessionLocal()

    try:
        sent_name, claim_name = _field_names(
            reminder_kind,
            recipient,
        )

        sent_col = getattr(Booking, sent_name)
        claim_col = getattr(Booking, claim_name)

        now = local_naive_now()
        stale_before = now - CLAIM_TTL

        result = db.execute(
            update(Booking)
            .where(
                Booking.id == booking_id,
                Booking.status == "confirmed",
                or_(
                    sent_col.is_(False),
                    sent_col.is_(None),
                ),
                or_(
                    claim_col.is_(None),
                    claim_col < stale_before,
                ),
            )
            .values(
                {
                    claim_name: now,
                }
            )
        )

        if result.rowcount != 1:
            db.rollback()
            return None

        db.commit()
        return now

    except Exception:
        db.rollback()
        logger.exception(
            "Не удалось claim reminder %s/%s для booking_id=%s",
            reminder_kind,
            recipient,
            booking_id,
        )
        return None

    finally:
        db.close()


def _claim_still_valid(
    booking_id: int,
    reminder_kind: str,
    recipient: str,
    claimed_at: datetime,
) -> bool:
    """
    Проверяет непосредственно перед отправкой, что:
    - запись всё ещё confirmed;
    - claim всё ещё принадлежит этому worker;
    - аккаунт получателя активен;
    - получатель всё ещё разрешает уведомления.
    """
    db = SessionLocal()

    try:
        _, claim_name = _field_names(
            reminder_kind,
            recipient,
        )
        claim_col = getattr(
            Booking,
            claim_name,
        )

        booking = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(
                    Booking.master
                ).joinedload(
                    Master.user
                ),
            )
            .where(
                Booking.id == booking_id,
                Booking.status == "confirmed",
                claim_col == claimed_at,
            )
        )

        if booking is None:
            return False

        if recipient == "client":
            recipient_user = booking.client
        else:
            recipient_user = (
                booking.master.user
                if booking.master is not None
                else None
            )

        if recipient_user is None:
            return False

        if not bool(
            getattr(
                recipient_user,
                "is_active",
                True,
            )
        ):
            return False

        if not _notifications_enabled(
            recipient_user
        ):
            return False

        return True

    finally:
        db.close()


def _finish_claim(
    booking_id: int,
    reminder_kind: str,
    recipient: str,
    claimed_at: datetime,
) -> bool:
    """
    Завершает именно наш claim после успешной отправки.
    """
    db = SessionLocal()

    try:
        sent_name, claim_name = _field_names(
            reminder_kind,
            recipient,
        )

        claim_col = getattr(Booking, claim_name)

        result = db.execute(
            update(Booking)
            .where(
                Booking.id == booking_id,
                Booking.status == "confirmed",
                claim_col == claimed_at,
            )
            .values(
                {
                    sent_name: True,
                    claim_name: None,
                }
            )
        )

        if result.rowcount != 1:
            db.rollback()
            return False

        db.commit()
        return True

    except Exception:
        db.rollback()
        logger.exception(
            "Не удалось завершить claim %s/%s для booking_id=%s",
            reminder_kind,
            recipient,
            booking_id,
        )
        return False

    finally:
        db.close()


def _release_claim(
    booking_id: int,
    reminder_kind: str,
    recipient: str,
    claimed_at: datetime,
) -> None:
    """
    При ошибке Telegram освобождает только наш claim,
    чтобы следующий запуск мог повторить отправку.
    """
    db = SessionLocal()

    try:
        _, claim_name = _field_names(
            reminder_kind,
            recipient,
        )

        claim_col = getattr(Booking, claim_name)

        db.execute(
            update(Booking)
            .where(
                Booking.id == booking_id,
                claim_col == claimed_at,
            )
            .values(
                {
                    claim_name: None,
                }
            )
        )
        db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "Не удалось освободить claim %s/%s для booking_id=%s",
            reminder_kind,
            recipient,
            booking_id,
        )

    finally:
        db.close()


def _title(
    reminder_kind: str,
) -> str:
    if reminder_kind == "24h":
        return (
            "Напоминание: запись примерно "
            "через 24 часа"
        )

    return (
        "Напоминание: запись примерно "
        "через 2 часа"
    )


async def _send_client(
    application: Application,
    payload: ReminderPayload,
) -> bool:
    if payload.client_sent:
        return True

    if (
        payload.client_telegram_id is None
        or not payload.client_notifications_enabled
    ):
        return False

    claimed_at = await asyncio.to_thread(
        _claim_recipient,
        payload.booking_id,
        payload.reminder_kind,
        "client",
    )

    if claimed_at is None:
        # Другой worker уже отправил или сейчас отправляет.
        return False

    if not await asyncio.to_thread(
        _claim_still_valid,
        payload.booking_id,
        payload.reminder_kind,
        "client",
        claimed_at,
    ):
        await asyncio.to_thread(
            _release_claim,
            payload.booking_id,
            payload.reminder_kind,
            "client",
            claimed_at,
        )
        return False

    try:
        await application.bot.send_message(
            chat_id=payload.client_telegram_id,
            text=(
                f"⏰ {_title(payload.reminder_kind)}\n\n"
                f"Запись #{payload.booking_id}\n"
                f"Услуга: {payload.service_title}\n"
                f"Мастер: {payload.master_name}\n"
                f"Дата: {payload.date_text}\n"
                f"Время: {payload.time_text}"
            ),
        )

        return await asyncio.to_thread(
            _finish_claim,
            payload.booking_id,
            payload.reminder_kind,
            "client",
            claimed_at,
        )

    except Exception:
        await asyncio.to_thread(
            _release_claim,
            payload.booking_id,
            payload.reminder_kind,
            "client",
            claimed_at,
        )
        logger.exception(
            "Не удалось отправить %s "
            "напоминание клиенту по записи %s",
            payload.reminder_kind,
            payload.booking_id,
        )
        return False


async def _send_master(
    application: Application,
    payload: ReminderPayload,
) -> bool:
    if payload.master_sent:
        return True

    if (
        payload.master_telegram_id is None
        or not payload.master_notifications_enabled
    ):
        return False

    claimed_at = await asyncio.to_thread(
        _claim_recipient,
        payload.booking_id,
        payload.reminder_kind,
        "master",
    )

    if claimed_at is None:
        return False

    if not await asyncio.to_thread(
        _claim_still_valid,
        payload.booking_id,
        payload.reminder_kind,
        "master",
        claimed_at,
    ):
        await asyncio.to_thread(
            _release_claim,
            payload.booking_id,
            payload.reminder_kind,
            "master",
            claimed_at,
        )
        return False

    try:
        await application.bot.send_message(
            chat_id=payload.master_telegram_id,
            text=(
                f"⏰ {_title(payload.reminder_kind)}\n\n"
                f"Запись #{payload.booking_id}\n"
                f"Клиент: {payload.client_name}\n"
                f"Услуга: {payload.service_title}\n"
                f"Дата: {payload.date_text}\n"
                f"Время: {payload.time_text}"
            ),
        )

        return await asyncio.to_thread(
            _finish_claim,
            payload.booking_id,
            payload.reminder_kind,
            "master",
            claimed_at,
        )

    except Exception:
        await asyncio.to_thread(
            _release_claim,
            payload.booking_id,
            payload.reminder_kind,
            "master",
            claimed_at,
        )
        logger.exception(
            "Не удалось отправить %s "
            "напоминание мастеру по записи %s",
            payload.reminder_kind,
            payload.booking_id,
        )
        return False


async def process_booking_reminders(
    application: Application,
) -> None:
    """
    Не блокирует Telegram event loop синхронными
    SQLAlchemy-запросами.

    БД читается/обновляется в worker thread,
    Telegram API остаётся полностью async.

    Перед отправкой каждый recipient атомарно claimed,
    поэтому несколько Railway workers не должны
    одновременно отправить одно и то же напоминание.
    """
    try:
        payloads = await asyncio.to_thread(
            _load_due_reminders
        )

        for payload in payloads:
            # Клиент и мастер независимы:
            # ошибка одного не мешает второму.
            await _send_client(
                application,
                payload,
            )

            await _send_master(
                application,
                payload,
            )

    except Exception:
        logger.exception(
            "Ошибка при обработке "
            "напоминаний о записях"
        )
