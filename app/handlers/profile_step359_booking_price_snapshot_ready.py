from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.models.booking import Booking
from app.models.master import Master
from app.repositories.user_repository import UserRepository
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


def profile_menu(
    bookings: list[Booking],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    now = local_naive_now()

    for booking_item in bookings:
        if (
            booking_item.status in {"new", "confirmed"}
            and booking_starts_at(booking_item) > now
        ):
            keyboard.append(
                [
                    KeyboardButton(
                        f"❌ Отменить запись #{booking_item.id}"
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
        input_field_placeholder="Выберите действие",
    )


async def profile(
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
        user = UserRepository.get_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Вы ещё не зарегистрированы. Отправьте /start."
            )
            return

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.service),
                    joinedload(Booking.master).joinedload(
                        Master.user
                    ),
                )
                .where(
                    Booking.client_id == user.id
                )
                .order_by(
                    Booking.booking_date.desc(),
                    Booking.booking_time.desc(),
                )
                .limit(10)
            ).unique().all()
        )

        notifications_text = (
            "✅ включены"
            if getattr(
                user,
                "notifications_enabled",
                True,
            )
            else "🔕 выключены"
        )

        profile_lines = [
            "👤 Личный кабинет",
            "",
            f"🧑 Имя: {user.first_name}",
            f"👤 Фамилия: {user.last_name or '—'}",
            (
                f"🌐 Username: @{user.username}"
                if user.username
                else "🌐 Username: —"
            ),
            f"📱 Телефон: {user.phone or '—'}",
            f"🎭 Роль: {user.role}",
            f"🕒 Часовой пояс: {user.timezone}",
            f"🔔 Уведомления: {notifications_text}",
            "",
            "📅 Последние записи:",
        ]

        if not bookings:
            profile_lines.append(
                "Записей пока нет."
            )
        else:
            for booking_item in bookings:
                service_title = (
                    booking_item.service.title
                    if booking_item.service
                    else "Услуга"
                )

                master_name = "Мастер"

                if (
                    booking_item.master
                    and booking_item.master.user
                    and booking_item.master.user.first_name
                ):
                    master_name = (
                        booking_item.master.user.first_name
                    )

                status_text = STATUS_NAMES.get(
                    booking_item.status,
                    booking_item.status,
                )

                booking_time_text = (
                    format_booking_time_for_user(
                        booking_date=booking_item.booking_date,
                        booking_time=booking_item.booking_time,
                        user=user,
                    )
                )

                profile_lines.extend(
                    [
                        "",
                        f"№{booking_item.id}",
                        f"💼 {service_title}",
                        f"💰 Цена: {booking_item.price_amount} сом",
                        f"👤 Мастер: {master_name}",
                        f"🕒 {booking_time_text}",
                        f"Статус: {status_text}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(profile_lines),
            reply_markup=profile_menu(
                bookings
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить личный кабинет. "
            "Попробуйте позже."
        )

    finally:
        db.close()


profile_handler = MessageHandler(
    filters.Regex(
        r"^👤 Личный кабинет$"
    ),
    profile,
)
