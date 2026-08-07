from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config.settings import settings
from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.salon import Salon
from app.models.user import User
from app.services.subscription_limits import (
    count_salon_branches,
    count_salon_masters,
)
from app.services.timezone import local_naive_now


PLANS = {
    "free": {
        "title": "Free",
        "price": 0,
        "masters": 1,
        "branches": 1,
        "description": "Для знакомства с сервисом",
    },
    "basic": {
        "title": "Basic",
        "price": 990,
        "masters": 3,
        "branches": 1,
        "description": "Для небольшого салона",
    },
    "pro": {
        "title": "Pro",
        "price": 2490,
        "masters": 10,
        "branches": 3,
        "description": "Для растущего бизнеса",
    },
    "business": {
        "title": "Business",
        "price": 4990,
        "masters": 50,
        "branches": 10,
        "description": "Для сети салонов",
    },
}


STATUS_NAMES = {
    "trial": "Пробный период",
    "active": "Активна",
    "expired": "Истекла",
    "cancelled": "Отменена",
}


def plans_menu(
    current_plan: str,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in PLANS.items():
        if plan_code == current_plan:
            text = (
                f"✅ Текущий тариф: "
                f"{plan['title']}"
            )
        else:
            text = (
                f"💳 Выбрать тариф "
                f"{plan['title']}"
            )

        keyboard.append(
            [KeyboardButton(text)]
        )

    keyboard.extend(
        [
            [KeyboardButton("🏢 Кабинет салона")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите тариф",
    )


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
        remaining = salon.trial_ends_at - now
        days = max(
            int(remaining.total_seconds() // 86400),
            0,
        )

        return (
            f"{status} · до "
            f"{salon.trial_ends_at.strftime('%d.%m.%Y')} "
            f"({days} дн.)"
        )

    if salon.subscription_ends_at is not None:
        return (
            f"{status} · до "
            f"{salon.subscription_ends_at.strftime('%d.%m.%Y')}"
        )

    return status


def platform_admin_ids() -> set[int]:
    result = set(settings.admin_telegram_ids)

    if settings.OWNER_TELEGRAM_ID is not None:
        result.add(settings.OWNER_TELEGRAM_ID)

    return result


async def show_available_plans(
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
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                    has_salon=False,
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

        lines = [
            "💳 Тарифы GlowFlow",
            "",
            f"🏢 Салон: {salon.name}",
            f"📌 Текущий тариф: "
            f"{PLANS.get(salon.plan, PLANS['free'])['title']}",
            f"🔐 Подписка: {subscription_status_text(salon)}",
            f"👥 Мастеров сейчас: {masters_count}",
            f"🏬 Филиалов сейчас: {branches_count}",
            "",
        ]

        for plan_code, plan in PLANS.items():
            marker = (
                "✅"
                if plan_code == salon.plan
                else "▫️"
            )

            lines.extend(
                [
                    (
                        f"{marker} {plan['title']} — "
                        f"{plan['price']} сом/мес."
                    ),
                    (
                        f"Мастеров: до "
                        f"{plan['masters']}"
                    ),
                    (
                        f"Филиалов: до "
                        f"{plan['branches']}"
                    ),
                    plan["description"],
                    "",
                ]
            )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=plans_menu(
                salon.plan
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить тарифы.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def request_plan_change(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    plan_title: str,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    selected_code = next(
        (
            code
            for code, plan in PLANS.items()
            if plan["title"].lower()
            == plan_title.lower()
        ),
        None,
    )

    if selected_code is None:
        await update.message.reply_text(
            "❌ Тариф не найден.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
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
                reply_markup=main_menu(
                    role=user.role if user else None,
                    telegram_id=update.effective_user.id,
                    has_salon=False,
                ),
            )
            return

        if not user.is_active:
            await update.message.reply_text(
                "❌ Ваш аккаунт временно отключён.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                    has_salon=True,
                ),
            )
            return

        if salon.plan == selected_code:
            await update.message.reply_text(
                "ℹ️ Этот тариф уже подключён.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        selected_plan = PLANS[selected_code]

        masters_count = count_salon_masters(
            db,
            salon.id,
        )
        branches_count = count_salon_branches(
            db,
            salon.id,
        )

        if masters_count > selected_plan["masters"]:
            await update.message.reply_text(
                "❌ На выбранный тариф пока нельзя перейти.\n\n"
                f"Сейчас мастеров: {masters_count}.\n"
                f"Лимит тарифа {selected_plan['title']}: "
                f"{selected_plan['masters']}.\n\n"
                "Сначала уменьшите количество мастеров.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        if branches_count > selected_plan["branches"]:
            await update.message.reply_text(
                "❌ На выбранный тариф пока нельзя перейти.\n\n"
                f"Сейчас филиалов: {branches_count}.\n"
                f"Лимит тарифа {selected_plan['title']}: "
                f"{selected_plan['branches']}.\n\n"
                "Сначала уменьшите количество филиалов.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        admin_ids = platform_admin_ids()

        if not admin_ids:
            await update.message.reply_text(
                "⚠️ Запрос не отправлен: "
                "в Railway ещё не настроен "
                "OWNER_TELEGRAM_ID или ADMIN_TELEGRAM_IDS.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        current_plan = PLANS.get(
            salon.plan,
            PLANS["free"],
        )

        admin_text = (
            "💳 Новый запрос на смену тарифа GlowFlow\n\n"
            f"🏢 Салон: {salon.name}\n"
            f"🆔 ID салона: {salon.id}\n"
            f"👤 Владелец: {user.first_name}\n"
            f"📱 Telegram ID: {user.telegram_id}\n"
            f"Текущий тариф: {current_plan['title']}\n"
            f"Запрошен: {selected_plan['title']}\n"
            f"Стоимость: {selected_plan['price']} сом/мес.\n"
            f"Мастеров: {masters_count}\n"
            f"Филиалов: {branches_count}\n\n"
            "Откройте «👑 Админ-панель» → "
            "«💳 Подписки салонов» для активации."
        )

        delivered = 0

        for admin_id in admin_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                )
                delivered += 1
            except Exception:
                continue

        if delivered == 0:
            await update.message.reply_text(
                "⚠️ Не удалось доставить запрос администраторам. "
                "Попробуйте позже.",
                reply_markup=plans_menu(
                    salon.plan
                ),
            )
            return

        context.user_data["requested_plan"] = selected_code

        await update.message.reply_text(
            "✅ Запрос на смену тарифа отправлен.\n\n"
            f"Новый тариф: {selected_plan['title']}\n"
            f"Стоимость: {selected_plan['price']} сом/мес.\n\n"
            "Текущий тариф останется активным, "
            "пока администратор не подтвердит смену.",
            reply_markup=plans_menu(
                salon.plan
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось отправить запрос на смену тарифа.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
