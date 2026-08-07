from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.plan_catalog import get_plan
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)
from app.services.timezone import local_naive_now


STATUS_NAMES = {
    "trial": "Пробный период",
    "active": "Активна",
    "expired": "Истекла",
    "cancelled": "Отменена",
}


def salon_owner_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🏢 Мой салон")],
            [KeyboardButton("🏬 Мои филиалы")],
            [KeyboardButton("👥 Мастера салона")],
            [KeyboardButton("➕ Добавить филиал")],
            [KeyboardButton("➕ Добавить мастера")],
            [KeyboardButton("🏬 Назначить филиал мастеру")],
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
    status = STATUS_NAMES.get(
        salon.subscription_status,
        salon.subscription_status,
    )

    now = local_naive_now()

    if (
        salon.subscription_status == "trial"
        and salon.trial_ends_at is not None
    ):
        remaining_seconds = (
            salon.trial_ends_at - now
        ).total_seconds()

        if remaining_seconds <= 0:
            return "Пробный период истёк"

        days = int(
            remaining_seconds // 86400
        )

        if days >= 1:
            remaining_text = f"{days} дн."
        else:
            hours = max(
                int(remaining_seconds // 3600),
                1,
            )
            remaining_text = f"{hours} ч."

        return (
            f"{status}\n"
            f"Осталось: {remaining_text}\n"
            f"До: {salon.trial_ends_at.strftime('%d.%m.%Y %H:%M')}"
        )

    if salon.subscription_ends_at is not None:
        return (
            f"{status}\n"
            f"До: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}"
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


def owner_main_menu(
    user: User | None,
    telegram_id: int,
    has_salon: bool,
) -> ReplyKeyboardMarkup:
    return main_menu(
        role=user.role if user else None,
        telegram_id=telegram_id,
        has_salon=has_salon,
    )


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
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        if not user.is_active:
            await update.message.reply_text(
                "❌ Ваш аккаунт временно отключён.",
                reply_markup=owner_main_menu(
                    user,
                    update.effective_user.id,
                    salon is not None,
                ),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "У вас пока нет активного салона.",
                reply_markup=owner_main_menu(
                    user,
                    update.effective_user.id,
                    False,
                ),
            )
            return

        masters_count = count_salon_masters(
            db,
            salon.id,
        )
        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        plan = get_plan(
            salon.plan
        )

        await update.message.reply_text(
            "🏢 Кабинет салона\n\n"
            f"ID: {salon.id}\n"
            f"Название: {salon.name}\n"
            f"Slug: {salon.slug}\n"
            f"Город: {salon.city or '—'}\n"
            f"Адрес: {salon.address or '—'}\n"
            f"Телефон: {salon.phone or '—'}\n\n"
            f"💳 Тариф: {plan['title']}\n"
            f"🔐 Подписка: {subscription_status_text(salon)}\n\n"
            f"👥 Мастеров: "
            f"{masters_count}/{plan['masters']}\n"
            f"🏬 Филиалов: "
            f"{branches_count}/{plan['branches']}",
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть кабинет салона.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
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
                reply_markup=owner_main_menu(
                    user,
                    update.effective_user.id,
                    False,
                ),
            )
            return

        salon = db.scalar(
            select(Salon)
            .options(joinedload(Salon.branches))
            .where(
                Salon.id == salon.id
            )
        )

        lines = ["🏬 Мои филиалы"]

        if not salon.branches:
            lines.extend(
                ["", "Филиалов пока нет."]
            )
        else:
            for branch in salon.branches:
                lines.extend(
                    [
                        "",
                        f"№{branch.id}",
                        f"Название: {branch.name}",
                        f"Адрес: {branch.address or '—'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить филиалы.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
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
                reply_markup=owner_main_menu(
                    user,
                    update.effective_user.id,
                    False,
                ),
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
            lines.extend(
                ["", "Мастеров пока нет."]
            )
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
                        (
                            "Приём записей: "
                            + (
                                "включён"
                                if master.booking_enabled
                                else "выключен"
                            )
                        ),
                        (
                            "Проверен: "
                            + (
                                "да"
                                if master.is_verified
                                else "нет"
                            )
                        ),
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров салона.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
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
                reply_markup=owner_main_menu(
                    user,
                    update.effective_user.id,
                    False,
                ),
            )
            return

        plan = get_plan(
            salon.plan
        )
        masters_count = count_salon_masters(
            db,
            salon.id,
        )
        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        await update.message.reply_text(
            "💳 Тариф и подписка\n\n"
            f"Текущий тариф: {plan['title']}\n"
            f"Стоимость: {plan['price']} сом/мес.\n"
            f"Статус: {subscription_status_text(salon)}\n\n"
            f"👥 Мастеров: "
            f"{masters_count}/{plan['masters']}\n"
            f"🏬 Филиалов: "
            f"{branches_count}/{plan['branches']}",
            reply_markup=salon_owner_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить подписку.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
