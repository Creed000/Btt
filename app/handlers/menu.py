import re
from datetime import datetime, timedelta

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.handlers.booking import booking
from app.handlers.profile import profile
from app.handlers.search import search
from app.keyboards.category import category_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.date import date_menu
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.keyboards.time import time_menu
from app.models.service import Service


CATEGORY_LABELS = {
    "hair": "Волосы",
    "nails": "Маникюр",
    "lashes": "Ресницы",
    "massage": "Массаж",
}

DATE_OFFSETS = {
    "📅 Сегодня": 0,
    "📅 Завтра": 1,
    "📅 Послезавтра": 2,
}

TIME_BUTTONS = {
    "🕘 09:00",
    "🕙 10:00",
    "🕚 11:00",
    "🕛 12:00",
    "🕐 13:00",
    "🕑 14:00",
    "🕒 15:00",
    "🕓 16:00",
    "🕔 17:00",
    "🕕 18:00",
}


def _get_first_service_id(master_id: int) -> int | None:
    db = SessionLocal()
    try:
        service = db.scalar(
            select(Service)
            .where(Service.master_id == master_id)
            .order_by(Service.id)
        )
        return service.id if service else None
    finally:
        db.close()


def _format_summary(context: ContextTypes.DEFAULT_TYPE) -> str:
    category = CATEGORY_LABELS.get(
        context.user_data.get("category", ""),
        context.user_data.get("category", "—"),
    )

    booking_date = context.user_data.get("booking_date")
    date_text = (
        booking_date.strftime("%d.%m.%Y")
        if booking_date
        else "—"
    )

    return (
        "📋 Подтверждение записи\n\n"
        f"🏙 Город: {context.user_data.get('city', '—')}\n"
        f"📂 Категория: {category}\n"
        f"👤 Мастер: {context.user_data.get('master_name', '—')}\n"
        f"📅 Дата: {date_text}\n"
        f"🕒 Время: {context.user_data.get('time_text', '—')}\n\n"
        "Подтвердить запись?"
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        return

    text = update.message.text.strip()

    if text == "📅 Записаться":
        context.user_data.clear()
        await booking(update, context)

    elif text == "👤 Личный кабинет":
        await profile(update, context)

    elif text == "🔍 Найти мастера":
        await search(update, context)

    elif text == "💼 Стать мастером":
        await update.message.reply_text(
            "💼 Регистрацию мастера подключим следующим этапом.",
            reply_markup=main_menu(),
        )

    elif text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ Добро пожаловать в BTT!\n\n"
            "📅 Записаться — запись к мастеру\n"
            "🔍 Найти мастера — поиск по каталогу\n"
            "👤 Личный кабинет — ваши записи\n"
            "⚙️ Настройки — настройки аккаунта",
            reply_markup=main_menu(),
        )

    elif text == "⚙️ Настройки":
        await update.message.reply_text(
            "⚙️ Настройки подключим следующим этапом.",
            reply_markup=main_menu(),
        )

    elif text in {"🏙 Бишкек", "🏙 Ош", "🏙 Джалал-Абад"}:
        context.user_data["city"] = text.replace("🏙", "").strip()
        await update.message.reply_text(
            "✅ Город выбран. Теперь выберите категорию.",
            reply_markup=category_menu(),
        )

    elif text in {"💇 Волосы", "💅 Маникюр", "👁 Ресницы", "💆 Массаж"}:
        category_map = {
            "💇 Волосы": "hair",
            "💅 Маникюр": "nails",
            "👁 Ресницы": "lashes",
            "💆 Массаж": "massage",
        }
        context.user_data["category"] = category_map[text]
        await update.message.reply_text(
            "👤 Выберите мастера",
            reply_markup=master_menu(),
        )

    elif text == "Мастеров пока нет":
        await update.message.reply_text(
            "Пока нет доступных мастеров.",
            reply_markup=main_menu(),
        )

    elif text.startswith("👤"):
        match = re.search(r"#(\d+)", text)
        if match is None:
            await update.message.reply_text(
                "Не удалось определить мастера. Выберите его кнопкой ещё раз.",
                reply_markup=master_menu(),
            )
            return

        master_id = int(match.group(1))
        service_id = _get_first_service_id(master_id)
        if service_id is None:
            await update.message.reply_text(
                "У этого мастера пока нет доступных услуг.",
                reply_markup=main_menu(),
            )
            return

        master_name = text.split("·")[0].replace("👤", "").strip()
        context.user_data["master_id"] = master_id
        context.user_data["master_name"] = master_name
        context.user_data["service_id"] = service_id

        await update.message.reply_text(
            "📅 Выберите дату",
            reply_markup=date_menu(),
        )

    elif text in DATE_OFFSETS:
        context.user_data["booking_date"] = (
            datetime.now().date() + timedelta(days=DATE_OFFSETS[text])
        )
        await update.message.reply_text(
            "🕒 Выберите время",
            reply_markup=time_menu(),
        )

    elif text in TIME_BUTTONS:
        time_text = text.split()[-1]
        context.user_data["booking_time"] = datetime.strptime(
            time_text,
            "%H:%M",
        ).time()
        context.user_data["time_text"] = time_text

        required = {
            "city",
            "category",
            "master_id",
            "service_id",
            "booking_date",
            "booking_time",
        }
        if not required.issubset(context.user_data):
            context.user_data.clear()
            await update.message.reply_text(
                "Сессия записи устарела. Начните запись заново.",
                reply_markup=main_menu(),
            )
            return

        await update.message.reply_text(
            _format_summary(context),
            reply_markup=confirm_menu(),
        )

    elif text == "✅ Подтвердить":
        try:
            create_booking(
                telegram_id=update.effective_user.id,
                master_id=context.user_data["master_id"],
                service_id=context.user_data["service_id"],
                booking_date=context.user_data["booking_date"],
                booking_time=context.user_data["booking_time"],
            )
        except KeyError:
            context.user_data.clear()
            await update.message.reply_text(
                "Сессия записи устарела. Начните запись заново.",
                reply_markup=main_menu(),
            )
            return
        except ValueError as error:
            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=time_menu(),
            )
            return
        except Exception:
            await update.message.reply_text(
                "❌ Не удалось создать запись. Попробуйте ещё раз позже.",
                reply_markup=main_menu(),
            )
            return

        context.user_data.clear()
        await update.message.reply_text(
            "🎉 Запись успешно создана!\n\n"
            "Она появится в вашем личном кабинете.",
            reply_markup=main_menu(),
        )

    elif text == "❌ Отменить":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Запись отменена.",
            reply_markup=main_menu(),
        )

    elif text == "⬅️ Назад":
        context.user_data.clear()
        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=main_menu(),
        )

    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню.",
            reply_markup=main_menu(),
        )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)

)
