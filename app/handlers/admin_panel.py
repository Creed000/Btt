from sqlalchemy import func, select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.master_catalog import available_masters_query


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


def user_main_menu(
    db,
    user: User | None,
    telegram_id: int,
) -> ReplyKeyboardMarkup:
    if user is None:
        return main_menu(
            telegram_id=telegram_id,
        )

    has_salon = (
        db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    )

    has_master = (
        db.scalar(
            select(Master.id)
            .where(
                Master.user_id == user.id
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=user.role,
        telegram_id=telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


async def open_admin_panel(
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
        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        if not can_manage_platform(user):
            await update.message.reply_text(
                "⛔ У вас нет доступа к "
                "админ-панели SaaS.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        users_count = (
            db.scalar(
                select(
                    func.count(User.id)
                )
            )
            or 0
        )

        active_users_count = (
            db.scalar(
                select(
                    func.count(User.id)
                ).where(
                    User.is_active.is_(True)
                )
            )
            or 0
        )

        masters_count = (
            db.scalar(
                select(
                    func.count(Master.id)
                )
            )
            or 0
        )

        verified_masters_count = (
            db.scalar(
                select(
                    func.count(Master.id)
                ).where(
                    Master.is_verified.is_(
                        True
                    )
                )
            )
            or 0
        )

        # Считаем не просто booking_enabled=True,
        # а мастеров, реально доступных клиенту:
        # active user + verified + city + service +
        # active salon subscription/branch where needed.
        available_masters = list(
            db.scalars(
                available_masters_query()
            ).unique().all()
        )
        available_masters_count = len(
            available_masters
        )

        services_count = (
            db.scalar(
                select(
                    func.count(Service.id)
                )
            )
            or 0
        )

        bookings_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                )
            )
            or 0
        )

        new_bookings_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                ).where(
                    Booking.status == "new"
                )
            )
            or 0
        )

        confirmed_bookings_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                ).where(
                    Booking.status
                    == "confirmed"
                )
            )
            or 0
        )

        completed_bookings_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                ).where(
                    Booking.status
                    == "completed"
                )
            )
            or 0
        )

        cancelled_bookings_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                ).where(
                    Booking.status
                    == "cancelled"
                )
            )
            or 0
        )

        salons_count = (
            db.scalar(
                select(
                    func.count(Salon.id)
                )
            )
            or 0
        )

        active_salons_count = (
            db.scalar(
                select(
                    func.count(Salon.id)
                ).where(
                    Salon.is_active.is_(True)
                )
            )
            or 0
        )

        await update.message.reply_text(
            "👑 Админ-панель GlowFlow\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"✅ Активных пользователей: "
            f"{active_users_count}\n\n"
            f"🧑‍💼 Мастеров: {masters_count}\n"
            f"🛡 Подтверждённых: "
            f"{verified_masters_count}\n"
            f"📅 Реально доступны для записи: "
            f"{available_masters_count}\n\n"
            f"🏢 Салонов: {salons_count}\n"
            f"✅ Активных салонов: "
            f"{active_salons_count}\n"
            f"💼 Услуг: {services_count}\n\n"
            f"📋 Всего записей: {bookings_count}\n"
            f"🕓 Новых: {new_bookings_count}\n"
            f"✅ Подтверждённых: "
            f"{confirmed_bookings_count}\n"
            f"🏁 Завершённых: "
            f"{completed_bookings_count}\n"
            f"❌ Отменённых: "
            f"{cancelled_bookings_count}",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        user = None

        try:
            user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
        except Exception:
            db.rollback()

        await update.message.reply_text(
            "❌ Не удалось открыть админ-панель.",
            reply_markup=user_main_menu(
                db,
                user,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()
