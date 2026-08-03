from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.repositories.user_repository import UserRepository


STATUS_NAMES = {
    "new": "🕓 Ожидает подтверждения",
    "confirmed": "✅ Подтверждена",
    "completed": "🏁 Завершена",
    "cancelled": "❌ Отменена",
}


async def profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    db = SessionLocal()

    try:
        user = UserRepository.get_by_telegram_id(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Вы ещё не зарегистрированы. Отправьте /start.",
                reply_markup=main_menu(),
            )
            return

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.service),
                    joinedload(Booking.master).joinedload(Master.user),
                )
                .where(Booking.client_id == user.id)
                .order_by(
                    Booking.booking_date.desc(),
                    Booking.booking_time.desc(),
                )
                .limit(5)
            ).unique().all()
        )

        profile_lines = [
            "👤 Личный кабинет",
            "",
            f"🧑 Имя: {user.first_name}",
            f"👤 Фамилия: {user.last_name or '—'}",
            f"🌐 Username: @{user.username}" if user.username else "🌐 Username: —",
            f"📱 Телефон: {user.phone or '—'}",
            f"🎭 Роль: {user.role}",
            f"🕒 Часовой пояс: {user.timezone}",
            "",
            "📅 Последние записи:",
        ]

        if not bookings:
            profile_lines.append("Записей пока нет.")
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
                    master_name = booking_item.master.user.first_name

                status_text = STATUS_NAMES.get(
                    booking_item.status,
                    booking_item.status,
                )

                profile_lines.extend(
                    [
                        "",
                        f"№{booking_item.id}",
                        f"💼 {service_title}",
                        f"👤 Мастер: {master_name}",
                        f"📅 {booking_item.booking_date.strftime('%d.%m.%Y')}",
                        f"🕒 {booking_item.booking_time.strftime('%H:%M')}",
                        f"Статус: {status_text}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(profile_lines),
            reply_markup=main_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить личный кабинет. Попробуйте позже.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


profile_handler = MessageHandler(
    filters.Regex(r"^👤 Личный кабинет$"),
    profile,
)
