from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.admin_controls import (
    admin_masters_actions_menu,
    admin_users_actions_menu,
)
from app.handlers.admin_panel import admin_menu
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.service import Service
from app.models.user import User
from app.services.access_control import can_manage_platform


STATUS_NAMES = {
    "new": "🕓 Новая",
    "confirmed": "✅ Подтверждена",
    "completed": "🏁 Завершена",
    "cancelled": "❌ Отменена",
}


def get_platform_admin(
    db,
    telegram_id: int,
) -> User | None:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if not can_manage_platform(user):
        return None

    return user


async def deny_platform_access(
    update: Update,
    role: str | None = None,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению SaaS-платформой.",
        reply_markup=main_menu(
            role=role,
            telegram_id=update.effective_user.id,
        ),
    )


async def show_admin_users(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_platform_access(update)
            return

        users = list(
            db.scalars(
                select(User)
                .order_by(User.id.desc())
                .limit(30)
            ).all()
        )

        lines = ["👥 Пользователи"]

        if not users:
            lines.extend(["", "Пользователей пока нет."])
        else:
            for user in users:
                username = (
                    f"@{user.username}"
                    if user.username
                    else "—"
                )

                lines.extend(
                    [
                        "",
                        f"ID: {user.id}",
                        f"Telegram ID: {user.telegram_id}",
                        f"Имя: {user.first_name}",
                        f"Username: {username}",
                        f"Роль: {user.role}",
                        f"Активен: {'да' if user.is_active else 'нет'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_users_actions_menu(users),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить пользователей.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def show_admin_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_platform_access(update)
            return

        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.city),
                    joinedload(Master.salon),
                    joinedload(Master.branch),
                )
                .order_by(Master.id.desc())
                .limit(30)
            ).unique().all()
        )

        lines = ["🧑‍💼 Мастера"]

        if not masters:
            lines.extend(["", "Мастеров пока нет."])
        else:
            for master in masters:
                name = (
                    master.user.first_name
                    if master.user
                    else "Без имени"
                )

                city = (
                    master.city.name
                    if master.city
                    else "не выбран"
                )

                salon = (
                    master.salon.name
                    if master.salon
                    else "самостоятельный мастер"
                )

                branch = (
                    master.branch.name
                    if master.branch
                    else "не назначен"
                )

                lines.extend(
                    [
                        "",
                        f"ID мастера: {master.id}",
                        f"Имя: {name}",
                        f"Город: {city}",
                        f"Салон: {salon}",
                        f"Филиал: {branch}",
                        f"Рейтинг: {master.rating:.1f}",
                        f"Приём записей: "
                        f"{'включён' if master.booking_enabled else 'выключен'}",
                        f"Проверен: "
                        f"{'да' if master.is_verified else 'нет'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_masters_actions_menu(masters),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def show_admin_bookings(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_platform_access(update)
            return

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.client),
                    joinedload(Booking.master).joinedload(Master.user),
                    joinedload(Booking.service),
                )
                .order_by(
                    Booking.booking_date.desc(),
                    Booking.booking_time.desc(),
                )
                .limit(30)
            ).unique().all()
        )

        lines = ["📅 Все записи"]

        if not bookings:
            lines.extend(["", "Записей пока нет."])
        else:
            for booking in bookings:
                client_name = (
                    booking.client.first_name
                    if booking.client
                    else "Клиент"
                )

                master_name = (
                    booking.master.user.first_name
                    if booking.master and booking.master.user
                    else "Мастер"
                )

                service_title = (
                    booking.service.title
                    if booking.service
                    else "Услуга"
                )

                status = STATUS_NAMES.get(
                    booking.status,
                    booking.status,
                )

                lines.extend(
                    [
                        "",
                        f"№{booking.id}",
                        f"Клиент: {client_name}",
                        f"Мастер: {master_name}",
                        f"Услуга: {service_title}",
                        f"Дата: {booking.booking_date.strftime('%d.%m.%Y')}",
                        f"Время: {booking.booking_time.strftime('%H:%M')}",
                        f"Статус: {status}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить записи.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def show_admin_statistics(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_platform_access(update)
            return

        users_count = db.scalar(
            select(func.count(User.id))
        ) or 0

        masters_count = db.scalar(
            select(func.count(Master.id))
        ) or 0

        services_count = db.scalar(
            select(func.count(Service.id))
        ) or 0

        bookings_count = db.scalar(
            select(func.count(Booking.id))
        ) or 0

        completed_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == "completed"
            )
        ) or 0

        cancelled_count = db.scalar(
            select(func.count(Booking.id)).where(
                Booking.status == "cancelled"
            )
        ) or 0

        await update.message.reply_text(
            "📊 Статистика SaaS\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"🧑‍💼 Мастеров: {masters_count}\n"
            f"💼 Услуг: {services_count}\n"
            f"📅 Всего записей: {bookings_count}\n"
            f"🏁 Завершённых: {completed_count}\n"
            f"❌ Отменённых: {cancelled_count}",
            reply_markup=admin_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить статистику.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()
