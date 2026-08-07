from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.admin_panel import admin_menu
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.plan_catalog import (
    PLAN_CATALOG,
    get_plan,
    get_plan_title,
)
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)
from app.services.timezone import local_naive_now


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
    keyboard: list[list[KeyboardButton]] = []

    for plan in PLAN_CATALOG.values():
        keyboard.append(
            [
                KeyboardButton(
                    f"✅ Активировать {plan['title']} "
                    f"для салона #{salon_id}"
                )
            ]
        )

    keyboard.extend(
        [
            [
                KeyboardButton(
                    f"⛔ Отключить подписку салона #{salon_id}"
                )
            ],
            [KeyboardButton("👑 Админ-панель")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
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
    plan = get_plan(plan_code)

    masters_count = count_salon_masters(
        db,
        salon.id,
    )
    branches_count = count_salon_branches(
        db,
        salon.id,
    )

    problems: list[str] = []

    if masters_count > plan["masters"]:
        problems.append(
            f"мастеров: {masters_count}, лимит: {plan['masters']}"
        )

    if branches_count > plan["branches"]:
        problems.append(
            f"филиалов: {branches_count}, лимит: {plan['branches']}"
        )

    if problems:
        details = "\n".join(
            f"• {problem}"
            for problem in problems
        )

        return (
            False,
            (
                f"Нельзя активировать тариф {plan['title']}.\n\n"
                f"{details}\n\n"
                "Сначала уменьшите количество ресурсов "
                "или выберите более высокий тариф."
            ),
        )

    return True, ""


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

        lines = ["💳 Подписки салонов GlowFlow"]

        if not salons:
            lines.extend(
                ["", "Салонов пока нет."]
            )
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

                masters_count = count_salon_masters(
                    db,
                    salon.id,
                )
                branches_count = count_salon_branches(
                    db,
                    salon.id,
                )

                lines.extend(
                    [
                        "",
                        f"ID салона: {salon.id}",
                        f"Название: {salon.name}",
                        f"Владелец: {owner_name}",
                        f"Тариф: {get_plan_title(salon.plan)}",
                        f"Статус: {salon.subscription_status}",
                        f"Мастеров: {masters_count}",
                        f"Филиалов: {branches_count}",
                        f"Пробный период до: {trial_end}",
                        f"Подписка до: {end_date}",
                        (
                            "Активен: "
                            + (
                                "да"
                                if salon.is_active
                                else "нет"
                            )
                        ),
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
            f"Текущий тариф: {get_plan_title(salon.plan)}\n"
            f"Статус: {salon.subscription_status}\n"
            f"Мастеров: {masters_count}\n"
            f"Филиалов: {branches_count}\n\n"
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

    if plan_code not in PLAN_CATALOG:
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
                f"❌ {reason}",
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
            f"Тариф: {get_plan_title(plan_code)}\n"
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

        db.execute(
            update(Master)
            .where(
                Master.salon_id == salon.id,
                Master.booking_enabled.is_(True),
            )
            .values(
                booking_enabled=False
            )
        )

        db.commit()

        await update.message.reply_text(
            f"⛔ Подписка салона «{salon.name}» отключена.\n\n"
            "Приём новых записей у мастеров этого салона "
            "автоматически выключен.",
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
