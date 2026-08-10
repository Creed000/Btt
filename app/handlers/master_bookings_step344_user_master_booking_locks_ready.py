from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.models.user import User
from app.services.booking_notifications import (
    notification_result_text,
    notify_client_about_status,
)
from app.services.booking_time_display import (
    format_booking_time_for_user,
)
from app.services.timezone import local_naive_now


STATUS_NAMES = {
    "new": "🕓 Ожидает подтверждения",
    "confirmed": "✅ Подтверждена",
    "completed": "🏁 Завершена",
    "cancelled": "❌ Отменена",
}


def booking_starts_at(
    booking: Booking,
) -> datetime:
    return datetime.combine(
        booking.booking_date,
        booking.booking_time,
    )


def booking_ends_at(
    booking: Booking,
) -> datetime:
    duration = (
        booking.service.duration
        if booking.service is not None
        else 30
    )

    return booking_starts_at(
        booking
    ) + timedelta(
        minutes=duration
    )


def master_bookings_menu(
    bookings: list[Booking],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    now = local_naive_now()

    for booking in bookings:
        starts_at = booking_starts_at(
            booking
        )
        ends_at = booking_ends_at(
            booking
        )

        if (
            booking.status == "new"
            and starts_at > now
        ):
            keyboard.append(
                [
                    KeyboardButton(
                        f"✅ Подтвердить запись #{booking.id}"
                    )
                ]
            )
            keyboard.append(
                [
                    KeyboardButton(
                        f"❌ Отменить заявку #{booking.id}"
                    )
                ]
            )

        elif booking.status == "confirmed":
            if starts_at > now:
                keyboard.append(
                    [
                        KeyboardButton(
                            f"❌ Отменить запись #{booking.id}"
                        )
                    ]
                )

            if ends_at <= now:
                keyboard.append(
                    [
                        KeyboardButton(
                            f"🏁 Завершить запись #{booking.id}"
                        )
                    ]
                )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление записями",
    )


def get_master_by_telegram_id(
    db,
    telegram_id: int,
) -> Master | None:
    return db.scalar(
        select(Master)
        .options(
            joinedload(Master.user),
        )
        .join(
            User,
            User.id == Master.user_id,
        )
        .where(
            User.telegram_id == telegram_id
        )
    )


async def show_master_bookings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        master = get_master_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден."
            )
            return

        if (
            master.user is None
            or not master.user.is_active
        ):
            await update.message.reply_text(
                "❌ Ваш аккаунт временно отключён."
            )
            return

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.client),
                    joinedload(Booking.service),
                )
                .where(
                    Booking.master_id == master.id
                )
                .order_by(
                    Booking.booking_date.desc(),
                    Booking.booking_time.desc(),
                )
                .limit(30)
            ).unique().all()
        )

        lines = [
            "📅 Мои записи",
            "",
        ]

        if not bookings:
            lines.append(
                "Записей пока нет."
            )
        else:
            for booking in bookings:
                client_name = (
                    booking.client.first_name
                    if booking.client
                    else "Клиент"
                )

                service_title = (
                    booking.service.title
                    if booking.service
                    else "Услуга"
                )

                status_text = STATUS_NAMES.get(
                    booking.status,
                    booking.status,
                )

                time_text = (
                    format_booking_time_for_user(
                        booking_date=booking.booking_date,
                        booking_time=booking.booking_time,
                        user=master.user,
                    )
                )

                lines.extend(
                    [
                        f"№{booking.id}",
                        f"👤 Клиент: {client_name}",
                        f"💼 {service_title}",
                        f"🕒 {time_text}",
                        f"Статус: {status_text}",
                        "",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=master_bookings_menu(
                bookings
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить записи мастера."
        )

    finally:
        db.close()


async def change_master_booking_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    booking_id: int,
    new_status: str,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    if new_status not in {
        "confirmed",
        "completed",
        "cancelled",
    }:
        await update.message.reply_text(
            "❌ Недопустимый статус записи."
        )
        return

    db = SessionLocal()

    try:
        master_preview = get_master_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if master_preview is None:
            raise ValueError(
                "Профиль мастера не найден."
            )

        # Админская блокировка пользователя с шага 339
        # использует порядок User -> Master. Берём те же
        # row-lock в том же порядке перед изменением Booking.
        locked_user = db.scalar(
            select(User)
            .where(
                User.id == master_preview.user_id
            )
            .with_for_update()
        )

        if locked_user is None or not locked_user.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        master = db.scalar(
            select(Master)
            .where(
                Master.id == master_preview.id,
                Master.user_id == locked_user.id,
            )
            .with_for_update()
        )

        if master is None:
            raise ValueError(
                "Профиль мастера больше не существует."
            )

        booking = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(Booking.service),
            )
            .where(
                Booking.id == booking_id,
                Booking.master_id == master.id,
            )
            .with_for_update()
        )

        if booking is None:
            raise ValueError(
                "Запись не найдена или принадлежит другому мастеру."
            )

        now = local_naive_now()
        starts_at = booking_starts_at(
            booking
        )
        ends_at = booking_ends_at(
            booking
        )

        if booking.status in {
            "completed",
            "cancelled",
        }:
            raise ValueError(
                "Статус завершённой или отменённой записи "
                "изменять нельзя."
            )

        if new_status == "confirmed":
            if booking.status != "new":
                raise ValueError(
                    "Подтвердить можно только новую заявку."
                )

            if starts_at <= now:
                raise ValueError(
                    "Прошедшую заявку подтвердить нельзя."
                )

        elif new_status == "cancelled":
            if booking.status not in {
                "new",
                "confirmed",
            }:
                raise ValueError(
                    "Эту запись нельзя отменить "
                    "в текущем статусе."
                )

            if starts_at <= now:
                raise ValueError(
                    "Прошедшую или уже начавшуюся запись "
                    "отменить через эту кнопку нельзя."
                )

        elif new_status == "completed":
            if booking.status != "confirmed":
                raise ValueError(
                    "Завершить можно только подтверждённую запись."
                )

            if ends_at > now:
                raise ValueError(
                    "Услуга ещё не закончилась. "
                    "Завершить запись можно после окончания "
                    "расчётного времени услуги."
                )

        booking.status = new_status
        db.commit()

        # Сохраняем необходимые связанные данные до закрытия сессии.
        db.expunge_all()

        notification_result = await notify_client_about_status(
            context.application,
            booking,
        )

        notification_text = notification_result_text(
            notification_result,
            "Клиент",
        )

        status_text = STATUS_NAMES.get(
            new_status,
            new_status,
        )

        await update.message.reply_text(
            f"✅ Запись #{booking_id}: {status_text}\n"
            f"{notification_text}"
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}"
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус записи."
        )

    finally:
        db.close()
