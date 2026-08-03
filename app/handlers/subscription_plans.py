from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.salon import Salon
from app.models.user import User


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


def plans_menu(current_plan: str) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for plan_code, plan in PLANS.items():
        if plan_code == current_plan:
            keyboard.append(
                [
                    KeyboardButton(
                        f"✅ Текущий тариф: {plan['title']}"
                    )
                ]
            )
        else:
            keyboard.append(
                [
                    KeyboardButton(
                        f"💳 Выбрать тариф {plan['title']}"
                    )
                ]
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
                "❌ Пользователь не найден.",
                reply_markup=main_menu(),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(role=user.role),
            )
            return

        lines = [
            "💳 Тарифы BTT",
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
                    f"{marker} {plan['title']} — {plan['price']} сом/мес.",
                    f"Мастеров: до {plan['masters']}",
                    f"Филиалов: до {plan['branches']}",
                    plan["description"],
                    "",
                ]
            )

        await update.message.reply_text(
            "\n".join(lines).strip(),
            reply_markup=plans_menu(salon.plan),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить тарифы.",
            reply_markup=main_menu(),
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

    for plan_code, plan in PLANS.items():
        if plan["title"].lower() == plan_title.lower():
            selected_code = plan_code
            break

    if selected_code is None:
        await update.message.reply_text(
            "❌ Тариф не найден.",
            reply_markup=main_menu(),
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
                reply_markup=main_menu(),
            )
            return

        if salon.plan == selected_code:
            await update.message.reply_text(
                "ℹ️ Этот тариф уже подключён.",
                reply_markup=plans_menu(salon.plan),
            )
            return

        context.user_data["requested_plan"] = selected_code

        plan = PLANS[selected_code]

        await update.message.reply_text(
            "🧾 Запрос на смену тарифа\n\n"
            f"Салон: {salon.name}\n"
            f"Новый тариф: {plan['title']}\n"
            f"Стоимость: {plan['price']} сом/мес.\n\n"
            "Онлайн-оплату подключим следующим этапом. "
            "Пока запрос сохранён в текущей сессии.",
            reply_markup=plans_menu(salon.plan),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось подготовить смену тарифа.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()
