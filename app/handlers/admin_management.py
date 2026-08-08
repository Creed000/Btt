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
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.access_control import (
    can_manage_platform,
    is_platform_admin,
    is_platform_owner,
)
from app.services.master_catalog import (
    available_masters_query,
)


STATUS_NAMES = {
    "new": "🕓 Новая",
    "confirmed": "✅ Подтверждена",
    "completed": "🏁 Завершена",
    "cancelled": "❌ Отменена",
}

LIST_LIMIT = 30


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


def user_main_menu(
    db,
    user: User | None,
    telegram_id: int,
):
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


async def deny_platform_access(
    update: Update,
    db,
    user: User | None,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению SaaS-платформой.",
        reply_markup=user_main_menu(
            db,
            user,
            update.effective_user.id,
        ),
    )


def platform_role_label(
    user: User,
) -> str:
    if is_platform_owner(
        user.telegram_id
    ):
        return "👑 Владелец платформы"

    if is_platform_admin(
        user.telegram_id
    ):
        return "🛡 Администратор платформы"

    return user.role or "client"


async def show_admin_users(
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
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            current_user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
            await deny_platform_access(
                update,
                db,
                current_user,
            )
            return

        total_count = (
            db.scalar(
                select(
                    func.count(User.id)
                )
            )
            or 0
        )

        users = list(
            db.scalars(
                select(User)
                .order_by(
                    User.id.desc()
                )
                .limit(
                    LIST_LIMIT
                )
            ).all()
        )

        lines = [
            "👥 Пользователи",
            "",
            f"Всего: {total_count}",
        ]

        if not users:
            lines.append(
                "Пользователей пока нет."
            )
        else:
            if total_count > LIST_LIMIT:
                lines.append(
                    f"Показаны последние {LIST_LIMIT}."
                )

            for user in users:
                username = (
                    f"@{user.username}"
                    if user.username
                    else "—"
                )

                first_name = (
                    user.first_name
                    or "Без имени"
                )

                lines.extend(
                    [
                        "",
                        f"ID: {user.id}",
                        f"Telegram ID: "
                        f"{user.telegram_id}",
                        f"Имя: {first_name}",
                        f"Username: {username}",
                        f"Роль: "
                        f"{platform_role_label(user)}",
                        "Аккаунт: "
                        f"{'✅ активен' if user.is_active else '⛔ отключён'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_users_actions_menu(
                users
            ),
        )

    except Exception:
        db.rollback()

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
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            current_user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
            await deny_platform_access(
                update,
                db,
                current_user,
            )
            return

        total_count = (
            db.scalar(
                select(
                    func.count(Master.id)
                )
            )
            or 0
        )

        available_ids = {
            master.id
            for master in db.scalars(
                available_masters_query()
            ).unique().all()
        }

        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.city),
                    joinedload(Master.salon),
                    joinedload(Master.branch),
                )
                .order_by(
                    Master.id.desc()
                )
                .limit(
                    LIST_LIMIT
                )
            ).unique().all()
        )

        lines = [
            "🧑‍💼 Мастера",
            "",
            f"Всего: {total_count}",
            f"Доступны клиентам: "
            f"{len(available_ids)}",
        ]

        if not masters:
            lines.append(
                "Мастеров пока нет."
            )
        else:
            if total_count > LIST_LIMIT:
                lines.append(
                    f"Показаны последние {LIST_LIMIT}."
                )

            for master in masters:
                name = (
                    master.user.first_name
                    if master.user
                    and master.user.first_name
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

                account_active = bool(
                    master.user
                    and master.user.is_active
                )

                client_available = (
                    master.id
                    in available_ids
                )

                lines.extend(
                    [
                        "",
                        f"ID мастера: {master.id}",
                        f"Имя: {name}",
                        f"Город: {city}",
                        f"Салон: {salon}",
                        f"Филиал: {branch}",
                        f"Рейтинг: "
                        f"{master.rating:.1f}",
                        "Аккаунт: "
                        f"{'✅ активен' if account_active else '⛔ отключён'}",
                        "Проверен: "
                        f"{'✅ да' if master.is_verified else '❌ нет'}",
                        "Переключатель записи: "
                        f"{'✅ включён' if master.booking_enabled else '⏸ выключен'}",
                        "Доступен клиентам: "
                        f"{'✅ да' if client_available else '❌ нет'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_masters_actions_menu(
                masters
            ),
        )

    except Exception:
        db.rollback()

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
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            current_user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
            await deny_platform_access(
                update,
                db,
                current_user,
            )
            return

        total_count = (
            db.scalar(
                select(
                    func.count(Booking.id)
                )
            )
            or 0
        )

        bookings = list(
            db.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.client),
                    joinedload(
                        Booking.master
                    ).joinedload(
                        Master.user
                    ),
                    joinedload(Booking.service),
                )
                .order_by(
                    Booking.booking_date.desc(),
                    Booking.booking_time.desc(),
                )
                .limit(
                    LIST_LIMIT
                )
            ).unique().all()
        )

        lines = [
            "📅 Все записи",
            "",
            f"Всего: {total_count}",
        ]

        if not bookings:
            lines.append(
                "Записей пока нет."
            )
        else:
            if total_count > LIST_LIMIT:
                lines.append(
                    f"Показаны последние {LIST_LIMIT}."
                )

            for booking in bookings:
                client_name = (
                    booking.client.first_name
                    if booking.client
                    and booking.client.first_name
                    else "Клиент"
                )

                master_name = (
                    booking.master.user.first_name
                    if booking.master
                    and booking.master.user
                    and booking.master.user.first_name
                    else "Мастер"
                )

                service_title = (
                    booking.service.title
                    if booking.service
                    else "Услуга"
                )

                status = (
                    STATUS_NAMES.get(
                        booking.status,
                        booking.status,
                    )
                )

                lines.extend(
                    [
                        "",
                        f"№{booking.id}",
                        f"Клиент: {client_name}",
                        f"Мастер: {master_name}",
                        f"Услуга: {service_title}",
                        "Дата: "
                        f"{booking.booking_date.strftime('%d.%m.%Y')}",
                        "Время: "
                        f"{booking.booking_time.strftime('%H:%M')}",
                        f"Статус: {status}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

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
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            current_user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
            await deny_platform_access(
                update,
                db,
                current_user,
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

        masters_count = (
            db.scalar(
                select(
                    func.count(Master.id)
                )
            )
            or 0
        )

        available_masters_count = len(
            list(
                db.scalars(
                    available_masters_query()
                ).unique().all()
            )
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

        status_counts = {
            status: (
                db.scalar(
                    select(
                        func.count(Booking.id)
                    ).where(
                        Booking.status
                        == status
                    )
                )
                or 0
            )
            for status in (
                "new",
                "confirmed",
                "completed",
                "cancelled",
            )
        }

        await update.message.reply_text(
            "📊 Статистика SaaS\n\n"
            f"👥 Пользователей: "
            f"{users_count}\n"
            f"🧑‍💼 Мастеров: "
            f"{masters_count}\n"
            f"📅 Доступны клиентам: "
            f"{available_masters_count}\n"
            f"💼 Услуг: "
            f"{services_count}\n\n"
            f"📋 Всего записей: "
            f"{bookings_count}\n"
            f"🕓 Новых: "
            f"{status_counts['new']}\n"
            f"✅ Подтверждённых: "
            f"{status_counts['confirmed']}\n"
            f"🏁 Завершённых: "
            f"{status_counts['completed']}\n"
            f"❌ Отменённых: "
            f"{status_counts['cancelled']}",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить статистику.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()
