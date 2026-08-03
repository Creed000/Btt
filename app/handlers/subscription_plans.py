from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User


SALON_PLANS = {
    "salon_free": {
        "title": "Salon Free",
        "price": 0,
        "masters": 1,
        "branches": 1,
        "description": "Для тестирования системы",
    },
    "salon_basic": {
        "title": "Salon Basic",
        "price": 1490,
        "masters": 3,
        "branches": 1,
        "description": "Для небольшого салона",
    },
    "salon_pro": {
        "title": "Salon Pro",
        "price": 3490,
        "masters": 10,
        "branches": 3,
        "description": "Для растущего салона",
    },
    "salon_business": {
        "title": "Salon Business",
        "price": 6990,
        "masters": 50,
        "branches": 10,
        "description": "Для сети салонов",
    },
}


MASTER_PLANS = {
    "master_free": {
        "title": "Master Free",
        "price": 0,
        "services": 3,
        "bookings_per_month": 30,
        "description": "Для начинающего мастера",
    },
    "master_start": {
        "title": "Master Start",
        "price": 390,
        "services": 10,
        "bookings_per_month": 150,
        "description": "Для индивидуального мастера",
    },
    "master_pro": {
        "title": "Master Pro",
        "price": 790,
        "services": 50,
        "bookings_per_month": 1000,
        "description": "Для активно работающего мастера",
    },
    "master_unlimited": {
        "title": "Master Unlimited",
        "price": 1290,
        "services": 9999,
        "bookings_per_month": 999999,
        "description": "Без ограничений",
    },
}


def salon_plans_menu(
    current_plan: str,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in SALON_PLANS.items():
        if plan_code == current_plan:
            label = f"✅ Текущий тариф: {plan['title']}"
        else:
            label = f"💳 Выбрать тариф {plan['title']}"

        keyboard.append([KeyboardButton(label)])

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
        input_field_placeholder="Тарифы для салона",
    )


def master_plans_menu(
    current_plan: str,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in MASTER_PLANS.items():
        if plan_code == current_plan:
            label = f"✅ Текущий тариф: {plan['title']}"
        else:
            label = f"💳 Выбрать тариф {plan['title']}"

        keyboard.append([KeyboardButton(label)])

    keyboard.extend(
        [
            [KeyboardButton("💼 Стать мастером")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Тарифы для мастера",
    )


def get_user(
    db,
    telegram_id: int,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )


async def show_subscription_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = get_user(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=main_menu(),
            )
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
        )

        master = db.scalar(
            select(Master).where(
                Master.user_id == user.id
            )
        )

        keyboard = []

        if salon is not None:
            keyboard.append(
                [KeyboardButton("🏢 Тарифы для салона")]
            )

        if master is not None:
            keyboard.append(
                [KeyboardButton("👤 Тарифы для мастера")]
            )

        if not keyboard:
            await update.message.reply_text(
                "У вас пока нет профиля мастера или салона.",
                reply_markup=main_menu(role=user.role),
            )
            return

        keyboard.append(
            [KeyboardButton("⬅️ Назад")]
        )

        await update.message.reply_text(
            "💳 Выберите тип подписки:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True,
            ),
        )

    finally:
        db.close()


async def show_salon_plans(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = get_user(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=main_menu(),
            )
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(role=user.role),
            )
            return

        current_plan = salon.plan or "salon_free"

        lines = [
            "🏢 Тарифы для салона",
            "",
        ]

        for code, plan in SALON_PLANS.items():
            marker = "✅" if code == current_plan else "▫️"

            lines.extend(
                [
                    f"{marker} {plan['title']} — {plan['price']} сом/мес.",
                    f"Мастеров: до {plan['masters']}",
                    f"Филиалов: до {plan['branches']}",
                    plan["description"],
                    "",
                ]
            )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=salon_plans_menu(current_plan),
        )

    finally:
        db.close()


async def show_master_plans(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = get_user(
            db,
            update.effective_user.id,
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=main_menu(),
            )
            return

        master = db.scalar(
            select(Master).where(
                Master.user_id == user.id
            )
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(role=user.role),
            )
            return

        current_plan = getattr(
            master,
            "plan",
            "master_free",
        )

        lines = [
            "👤 Тарифы для индивидуального мастера",
            "",
        ]

        for code, plan in MASTER_PLANS.items():
            marker = "✅" if code == current_plan else "▫️"

            bookings_limit = (
                "без ограничений"
                if plan["bookings_per_month"] >= 999999
                else str(plan["bookings_per_month"])
            )

            services_limit = (
                "без ограничений"
                if plan["services"] >= 9999
                else str(plan["services"])
            )

            lines.extend(
                [
                    f"{marker} {plan['title']} — {plan['price']} сом/мес.",
                    f"Услуг: {services_limit}",
                    f"Записей в месяц: {bookings_limit}",
                    plan["description"],
                    "",
                ]
            )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=master_plans_menu(current_plan),
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

    selected_code = None
    selected_type = None
    selected_plan = None

    for code, plan in SALON_PLANS.items():
        if plan["title"].lower() == plan_title.lower():
            selected_code = code
            selected_type = "salon"
            selected_plan = plan
            break

    if selected_code is None:
        for code, plan in MASTER_PLANS.items():
            if plan["title"].lower() == plan_title.lower():
                selected_code = code
                selected_type = "master"
                selected_plan = plan
                break

    if selected_code is None or selected_plan is None:
        await update.message.reply_text(
            "❌ Тариф не найден.",
            reply_markup=main_menu(),
        )
        return

    context.user_data["requested_plan"] = selected_code
    context.user_data["requested_plan_type"] = selected_type

    await update.message.reply_text(
        "🧾 Запрос на смену тарифа\n\n"
        f"Тип: {'Салон' if selected_type == 'salon' else 'Мастер'}\n"
        f"Тариф: {selected_plan['title']}\n"
        f"Стоимость: {selected_plan['price']} сом/мес.\n\n"
        "Запрос сохранён. Онлайн-оплату подключим следующим этапом.",
        reply_markup=main_menu(),
    )
