from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.admin_panel import admin_menu
from app.keyboards.main import main_menu
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
    get_plan_limits,
)
from app.services.timezone import local_naive_now


PLAN_TITLES = {
    "free": "Free",
    "basic": "Basic",
    "pro": "Pro",
    "business": "Business",
}


def salon_subscription_actions_menu(
    salons: list[Salon],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for salon in salons:
        keyboard.append(
            [
                KeyboardButton(
                    f"💳 Управлять салоном #{salon.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("👑 Админ-панель")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите салон",
    )


def salon_plan_menu(
    salon_id: int,
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    f"✅ Активировать Free для салона #{salon_id}"
                )
            ],
            [
                KeyboardButton(
                    f"✅ Активировать Basic для салона #{salon_id}"
                )
            ],
            [
                KeyboardButton(
                    f"✅ Активировать Pro для салона #{salon_id}"
                )
            ],
            [
                KeyboardButton(
                    f"✅ Активировать Business для салона #{salon_id}"
                )
            ],
            [
                KeyboardButton(
                    f"⛔ Отключить подписку салона #{salon_id}"
                )
            ],
            [KeyboardButton("👑 Админ-панель")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие",
    )


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


async def deny_access(
    update: Update,
    role: str | None = None,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению подписками SaaS.",
        reply_markup=main_menu(
            role=role,
            telegram_id=update.effective_user.id,
        ),
    )


def validate_plan_capacity(
    db,
    salon: Salon,
    plan_code: str,
) -> tuple[bool, str]:
    limits = get_plan_limits(
        plan_code
    )

    masters_count = count_salon_masters(
        db,
        salon.id,
    )
    branches_count = count_salon_branches(
        db,
        salon.id,
    )

    problems: list[str] = []

    if masters_count > limits["masters"]:
        problems.append(
            f"мастеров: {masters_count}, "
            f"доступно: {limits['masters']}"
        )

    if branches_count > limits["branches"]:
        problems.append(
            f"филиалов: {branches_count}, "
            f"доступно: {limits['branches']}"
        )

    if not problems:
        return True, ""

    return (
        False,
        (
            f"Нельзя активировать тариф {PLAN_TITLES[plan_code]}.\n\n"
            "Текущие ресурсы превышают его лимиты:\n"
            + "\n".join(
                f"• {problem}"
                for problem in problems
            )
            + "\n\nСначала уменьшите количество мастеров "
            "или филиалов либо выберите более высокий тариф."
        ),
    )


async def show_salons_for_subscription(
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
            await deny_access(update)
            return

        salons = list(
            db.scalars(
                select(Salon)
                .options(joinedload(Salon.owner))
                .order_by(Salon.id.desc())
                .limit(50)
            ).unique().all()
        )

        lines = ["💳 Подписки салонов"]

        if not salons:
            lines.extend(["", "Салонов пока нет."])
        else:
            for salon in salons:
                owner_name = (
                    salon.owner.first_name
                    if salon.owner
                    else "—"
                )

                end_date = (
                    salon.subscription_ends_at.strftime(
                        "%d.%m.%Y %H:%M"
                    )
                    if salon.subscription_ends_at
                    else "—"
                )

                trial_end = (
                    salon.trial_ends_at.strftime(
                        "%d.%m.%Y %H:%M"
                    )
                    if salon.trial_ends_at
                    else "—"
                )

                lines.extend(
                    [
                        "",
                        f"ID салона: {salon.id}",
                        f"Название: {salon.name}",
                        f"Владелец: {owner_name}",
                        f"Тариф: {salon.plan}",
                        f"Статус: {salon.subscription_status}",
                        f"Пробный период до: {trial_end}",
                        f"Подписка до: {end_date}",
                        f"Активен: {'да' if salon.is_active else 'нет'}",
                    ]
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=salon_subscription_actions_menu(
                salons
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить подписки салонов.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def open_salon_subscription_control(
    update: Update,
    salon_id: int,
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
            await deny_access(update)
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.id == salon_id
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон не найден.",
                reply_markup=admin_menu(),
            )
            return

        limits = get_plan_limits(
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
            "💳 Управление подпиской\n\n"
            f"Салон: {salon.name}\n"
            f"Текущий тариф: {salon.plan}\n"
            f"Статус: {salon.subscription_status}\n"
            f"Мастера: {masters_count}/{limits['masters']}\n"
            f"Филиалы: {branches_count}/{limits['branches']}\n\n"
            "Выберите действие:",
            reply_markup=salon_plan_menu(
                salon.id
            ),
        )

    finally:
        db.close()


async def activate_salon_plan(
    update: Update,
    salon_id: int,
    plan_code: str,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    if plan_code not in PLAN_TITLES:
        await update.message.reply_text(
            "❌ Неизвестный тариф.",
            reply_markup=admin_menu(),
        )
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.id == salon_id
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон не найден.",
                reply_markup=admin_menu(),
            )
            return

        allowed, reason = validate_plan_capacity(
            db,
            salon,
            plan_code,
        )

        if not allowed:
            await update.message.reply_text(
                f"⛔ {reason}",
                reply_markup=salon_plan_menu(
                    salon.id
                ),
            )
            return

        now = local_naive_now()

        salon.plan = plan_code
        salon.subscription_status = "active"
        salon.subscription_ends_at = (
            now + timedelta(days=30)
        )
        salon.is_active = True
        salon.updated_at = now

        db.commit()

        await update.message.reply_text(
            "✅ Подписка активирована!\n\n"
            f"Салон: {salon.name}\n"
            f"Тариф: {PLAN_TITLES[plan_code]}\n"
            f"Активна до: "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось активировать подписку.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def disable_salon_subscription(
    update: Update,
    salon_id: int,
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
            await deny_access(update)
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.id == salon_id
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Салон не найден.",
                reply_markup=admin_menu(),
            )
            return

        now = local_naive_now()

        salon.subscription_status = "cancelled"
        salon.subscription_ends_at = now
        salon.updated_at = now

        db.commit()

        await update.message.reply_text(
            f"⛔ Подписка салона «{salon.name}» отключена.",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отключить подписку.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()
