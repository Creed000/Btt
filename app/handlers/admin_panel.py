from sqlalchemy import func, select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.service import Service
from app.models.user import User
from app.services.access_control import can_manage_platform


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("👥 Пользователи")],
            [KeyboardButton("🧑‍💼 Мастера")],
            [KeyboardButton("📅 Все записи")],
            [KeyboardButton("📊 Статистика")],
            [KeyboardButton("💳 Подписки салонов")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Админ-панель",
    )


async def open_admin_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if not can_manage_platform(user):
            role = user.role if user is not None else None

            await update.message.reply_text(
                "⛔ У вас нет доступа к админ-панели SaaS.",
                reply_markup=main_menu(
                    role=role,
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        users_count = db.scalar(
            select(func.count(User.id))
        ) or 0

        active_users_count = db.scalar(
            select(func.count(User.id)).where(
                User.is_active.is_(True)
            )
        ) or 0

        masters_count = db.scalar(
            select(func.count(Master.id))
        ) or 0

        active_masters_count = db.scalar(
            select(func.count(Master.id)).where(
                Master.booking_enabled.is_(True)
            )
        ) or 0

        services_count = db.scalar(
            select(func.count(Service.id))
        ) or 0

        bookings_count = db.scalar(
            select(func.count(Booking.id))
        ) or 0

        new_bookings_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == "new"
            )
        ) or 0

        confirmed_bookings_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == "confirmed"
            )
        ) or 0

        await update.message.reply_text(
            "👑 Админ-панель SaaS\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"✅ Активных пользователей: {active_users_count}\n"
            f"🧑‍💼 Мастеров: {masters_count}\n"
            f"📅 Принимают записи: {active_masters_count}\n"
            f"💼 Услуг: {services_count}\n"
            f"📋 Всего записей: {bookings_count}\n"
            f"🕓 Новых записей: {new_bookings_count}\n"
            f"✅ Подтверждённых: {confirmed_bookings_count}",
            reply_markup=admin_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть админ-панель.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
