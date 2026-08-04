from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User


def salon_owner_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🏢 Мой салон")],
            [KeyboardButton("🏬 Мои филиалы")],
            [KeyboardButton("👥 Мастера салона")],
            [KeyboardButton("➕ Добавить филиал")],
            [KeyboardButton("➕ Добавить мастера")],
            [KeyboardButton("💳 Тариф и подписка")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Кабинет владельца",
    )


def subscription_status_text(
    salon: Salon,
) -> str:
    status_names = {
        "trial": "Пробный период",
        "active": "Активна",
        "expired": "Истекла",
        "cancelled": "Отменена",
    }

    status = status_names.get(
        salon.subscription_status,
        salon.subscription_status,
    )

    if salon.subscription_status == "trial" and salon.trial_ends_at:
        remaining = salon.trial_ends_at - datetime.utcnow()
        days = max(remaining.days, 0)

        return (
            f"{status}\n"
            f"Осталось дней: {days}\n"
            f"До: {salon.trial_ends_at.strftime('%d.%m.%Y')}"
        )

    if salon.subscription_ends_at:
        return (
            f"{status}\n"
            f"До: {salon.subscription_ends_at.strftime('%d.%m.%Y')}"
        )

    return status


def get_owner_and_salon(
    db,
    telegram_id: int,
) -> tuple[User | None, Salon | None]:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if user is None:
        return None, None

    salon = db.scalar(
        select(Salon).where(
            Salon.owner_id == user.id,
            Salon.is_active.is_(True),
        )
    )

    return user, salon


async def open_salon_dashboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(),
            )
            return

        if user.role not in {"owner", "admin"}:
            await update.message.reply_text(
                "⛔ Кабинет салона доступен только владельцу.",
                reply_markup=main_menu(role=user.role),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "У вас пока нет активного салона.",
                reply_markup=main_menu(role=user.role),
            )
            return

        salon = db.scalar(
            select(Salon)
            .options(joinedload(Salon.branches))
            .where(Salon.id == salon.id)
        )

        masters_count = len(
            db.scalars(
                select(Master).where(
                    Master.salon_id == salon.id
                )
            ).all()
        )

        await update.message.reply_text(
            "🏢 Кабинет салона\n\n"
            f"ID: {salon.id}\n"
            f"Название: {salon.name}\n"
            f"Slug: {salon.slug}\n"
            f"Город: {salon.city or '—'}\n"
            f"Адрес: {salon.address or '—'}\n"
            f"Телефон: {salon.phone or '—'}\n"
            f"Филиалов: {len(salon.branches)}\n"
            f"Мастеров: {masters_count}\n"
            f"Тариф: {salon.plan}\n"
            f"Подписка: {subscription_status_text(salon)}",
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть кабинет салона.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def show_salon_branches(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if user is None or salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(),
            )
            return

        salon = db.scalar(
            select(Salon)
            .options(joinedload(Salon.branches))
            .where(Salon.id == salon.id)
        )

        lines = ["🏬 Мои филиалы"]

        if not salon.branches:
            lines.extend(["", "Филиалов пока нет."])
        else:
            for branch in salon.branches:
                lines.extend(
                    [
                        "",
                        f"№{branch.id}",
                        f"Название: {branch.name}",
                        f"Адрес: {branch.address}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить филиалы.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def show_salon_masters(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if user is None or salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(),
            )
            return

        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.branch),
                )
                .where(
                    Master.salon_id == salon.id
                )
                .order_by(Master.id)
            ).unique().all()
        )

        lines = ["👥 Мастера салона"]

        if not masters:
            lines.extend(["", "Мастеров пока нет."])
        else:
            for master in masters:
                name = (
                    master.user.first_name
                    if master.user
                    else "Без имени"
                )

                branch_name = (
                    master.branch.name
                    if master.branch
                    else "не назначен"
                )

                lines.extend(
                    [
                        "",
                        f"ID мастера: {master.id}",
                        f"Имя: {name}",
                        f"Филиал: {branch_name}",
                        f"Рейтинг: {master.rating:.1f}",
                        f"Приём записей: "
                        f"{'включён' if master.booking_enabled else 'выключен'}",
                        f"Проверен: "
                        f"{'да' if master.is_verified else 'нет'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров салона.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def show_salon_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if user is None or salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(),
            )
            return

        await update.message.reply_text(
            "💳 Тариф и подписка\n\n"
            f"Текущий тариф: {salon.plan}\n"
            f"Статус: {subscription_status_text(salon)}",
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить подписку.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()
