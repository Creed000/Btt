from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.city import City
from app.models.master import Master
from app.models.user import User


CITY_BUTTONS = {
    "🏙 Бишкек": "Бишкек",
    "🏙 Ош": "Ош",
    "🏙 Джалал-Абад": "Джалал-Абад",
}


def master_city_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🏙 Бишкек")],
            [KeyboardButton("🏙 Ош")],
            [KeyboardButton("🏙 Джалал-Абад")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите город мастера",
    )


async def begin_master_city_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    context.user_data["master_city_selection"] = True

    await update.message.reply_text(
        "🏙 Выберите город, в котором вы принимаете клиентов:",
        reply_markup=master_city_menu(),
    )


async def process_master_city_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not context.user_data.get("master_city_selection"):
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "⬅️ Назад":
        context.user_data.pop("master_city_selection", None)

        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=main_menu(),
        )
        return True

    city_name = CITY_BUTTONS.get(text)

    if city_name is None:
        await update.message.reply_text(
            "Выберите город с помощью кнопок."
        )
        return True

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(),
            )
            context.user_data.pop("master_city_selection", None)
            return True

        master = db.scalar(
            select(Master).where(
                Master.user_id == user.id
            )
        )

        if master is None:
            await update.message.reply_text(
                "❌ Сначала создайте профиль мастера.",
                reply_markup=main_menu(),
            )
            context.user_data.pop("master_city_selection", None)
            return True

        city = db.scalar(
            select(City).where(
                City.name == city_name
            )
        )

        if city is None:
            city = City(
                name=city_name,
                is_active=True,
            )
            db.add(city)
            db.flush()

        master.city_id = city.id
        db.commit()

        context.user_data.pop("master_city_selection", None)

        await update.message.reply_text(
            f"✅ Город мастера сохранён: {city_name}",
            reply_markup=main_menu(),
        )
        return True

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось сохранить город мастера.",
            reply_markup=main_menu(),
        )
        context.user_data.pop("master_city_selection", None)
        return True

    finally:
        db.close()
