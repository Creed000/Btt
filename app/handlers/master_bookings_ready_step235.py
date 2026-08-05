from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.user import User
from app.services.booking_notifications import (
    notification_result_text,
    notify_client_about_status,
)
from app.services.timezone import local_naive_now


STATUS_NAMES = {
    "new": "🕓 Новая",
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
    ) + timedelta(minutes=duration)


def master_bookings_menu(
    bookings: list[Booking],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    now = local_naive_now()

    for booking in bookings:
        starts_at = booking_starts_at(
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
            ends_at = booking_ends_at(
                booking
            )

            if ends_at <= now:
                keyboard.append(
                    [
                        KeyboardButton(
                            f"🏁 Завершить запись #{booking.id}"
                        )
                    ]
                )
            elif starts_at > now:
                keyboard.append(
                    [
                        KeyboardButton(
                            f"❌ Отменить заявку #{booking.id}"
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
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if user is None:
        return None

    return db.scalar(
        select(Master).where(
            Master.user_id == user.id
        )
    )


async def show_master_bookings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_master_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
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
                    Booking.booking_date.asc(),
                    Booking.booking_time.asc(),
                )
                .limit(20)
            ).unique().all()
        )

        lines = ["📅 Записи мастера"]

        if not bookings:
            lines.extend(
                [
                    "",
                    "У вас пока нет записей.",
                ]
            )
        else:
            for booking in bookings:
                client_name = (
                    booking.client.first_name
                    if booking.client
                    else "Клиент"
                )

                client_phone = (
                    booking.client.phone
                    if booking.client
                    and booking.client.phone
                    else "—"
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

                lines.extend(
                    [
                        "",
                        f"№{booking.id}",
                        f"👤 Клиент: {client_name}",
                        f"📱 Телефон: {client_phone}",
                        f"💼 Услуга: {service_title}",
                        (
                            "📅 Дата: "
                            f"{booking.booking_date.strftime('%d.%m.%Y')}"
                        ),
                        (
                            "🕒 Время: "
                            f"{booking.booking_time.strftime('%H:%M')}"
                        ),
                        f"Статус: {status_text}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=master_bookings_menu(
                bookings
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить записи мастера.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def change_master_booking_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    booking_id: int,
    new_status: str,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_master_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        booking = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(Booking.service),
                joinedload(Booking.master).joinedload(
                    Master.user
                ),
            )
            .where(
                Booking.id == booking_id,
                Booking.master_id == master.id,
            )
        )

        if booking is None:
            await update.message.reply_text(
                "❌ Запись не найдена или принадлежит другому мастеру.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        allowed_transitions = {
            "new": {"confirmed", "cancelled"},
            "confirmed": {"completed", "cancelled"},
            "completed": set(),
            "cancelled": set(),
        }

        if new_status not in allowed_transitions.get(
            booking.status,
            set(),
        ):
            await update.message.reply_text(
                "❌ Нельзя изменить запись из текущего статуса.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        now = local_naive_now()
        starts_at = booking_starts_at(
            booking
        )

        if (
            new_status in {"confirmed", "cancelled"}
            and starts_at <= now
        ):
            await update.message.reply_text(
                "❌ Прошедшую запись нельзя подтвердить или отменить.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        if new_status == "completed":
            ends_at = booking_ends_at(
                booking
            )

            if ends_at > now:
                await update.message.reply_text(
                    "❌ Нельзя завершить запись до окончания услуги.",
                    reply_markup=main_menu(
                        telegram_id=update.effective_user.id,
                    ),
                )
                return

        booking.status = new_status
        db.commit()

        notification_result = (
            await notify_client_about_status(
                context.application,
                booking,
            )
        )

        result_messages = {
            "confirmed": (
                f"✅ Запись #{booking_id} подтверждена."
            ),
            "completed": (
                f"🏁 Запись #{booking_id} завершена."
            ),
            "cancelled": (
                f"❌ Запись #{booking_id} отменена."
            ),
        }

        notification_text = notification_result_text(
            notification_result,
            "Клиент",
        )

        await update.message.reply_text(
            f"{result_messages[new_status]}\n"
            f"{notification_text}",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус записи.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
