from datetime import date, datetime

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.master_day_off import MasterDayOff
from app.models.user import User


def day_off_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("➕ Добавить выходной")],
            [KeyboardButton("📋 Мои выходные даты")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выходные даты",
    )


def day_off_cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("❌ Отменить добавление выходного")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите дату",
    )


def day_off_delete_menu(
    days_off: list[MasterDayOff],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for item in days_off:
        keyboard.append(
            [
                KeyboardButton(
                    f"🗑 Удалить выходной #{item.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("➕ Добавить выходной")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление выходными",
    )


def clear_day_off_setup(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "day_off_setup",
        "day_off_date",
    ):
        context.user_data.pop(key, None)


def get_master(
    db,
    telegram_id: int,
) -> Master | None:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if user is None:
        return None

    return db.scalar(
        select(Master).where(
            Master.user_id == user.id
        )
    )


async def open_day_off_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "🏖 Выходные даты мастера\n\n"
        "Здесь можно добавить отпуск, болезнь или другой нерабочий день.",
        reply_markup=day_off_menu(),
    )


async def begin_day_off_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(),
            )
            return

    finally:
        db.close()

    clear_day_off_setup(context)
    context.user_data["day_off_setup"] = "date"

    await update.message.reply_text(
        "➕ Добавление выходного\n\n"
        "Введите дату в формате ДД.ММ.ГГГГ.\n\n"
        "Например: 15.08.2026",
        reply_markup=day_off_cancel_menu(),
    )


async def process_day_off_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if context.user_data.get("day_off_setup") is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить добавление выходного":
        clear_day_off_setup(context)

        await update.message.reply_text(
            "❌ Добавление выходного отменено.",
            reply_markup=day_off_menu(),
        )
        return True

    try:
        selected_date = datetime.strptime(
            text,
            "%d.%m.%Y",
        ).date()
    except ValueError:
        await update.message.reply_text(
            "Введите дату в формате ДД.ММ.ГГГГ.\n"
            "Например: 15.08.2026"
        )
        return True

    if selected_date < date.today():
        await update.message.reply_text(
            "Нельзя добавить прошедшую дату."
        )
        return True

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )

        if master is None:
            raise ValueError(
                "Профиль мастера не найден."
            )

        existing = db.scalar(
            select(MasterDayOff).where(
                MasterDayOff.master_id == master.id,
                MasterDayOff.day_off_date == selected_date,
            )
        )

        if existing is not None:
            raise ValueError(
                "Эта дата уже добавлена как выходной."
            )

        day_off = MasterDayOff(
            master_id=master.id,
            day_off_date=selected_date,
        )

        db.add(day_off)
        db.commit()

    except ValueError as error:
        db.rollback()
        clear_day_off_setup(context)

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=day_off_menu(),
        )
        return True

    except Exception:
        db.rollback()
        clear_day_off_setup(context)

        await update.message.reply_text(
            "❌ Не удалось сохранить выходной.",
            reply_markup=day_off_menu(),
        )
        return True

    finally:
        db.close()

    clear_day_off_setup(context)

    await update.message.reply_text(
        "✅ Выходной добавлен!\n\n"
        f"Дата: {selected_date.strftime('%d.%m.%Y')}",
        reply_markup=day_off_menu(),
    )
    return True


async def show_master_days_off(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(),
            )
            return

        days_off = list(
            db.scalars(
                select(MasterDayOff)
                .where(
                    MasterDayOff.master_id == master.id,
                    MasterDayOff.day_off_date >= date.today(),
                )
                .order_by(MasterDayOff.day_off_date)
            ).all()
        )

        lines = ["📋 Мои выходные даты"]

        if not days_off:
            lines.extend(
                [
                    "",
                    "Будущих выходных дат пока нет.",
                ]
            )
        else:
            for item in days_off:
                reason = (
                    f" — {item.reason}"
                    if item.reason
                    else ""
                )

                lines.append(
                    f"#{item.id} · "
                    f"{item.day_off_date.strftime('%d.%m.%Y')}"
                    f"{reason}"
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=day_off_delete_menu(days_off),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить выходные даты.",
            reply_markup=day_off_menu(),
        )

    finally:
        db.close()


async def delete_master_day_off(
    update: Update,
    day_off_id: int,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )

        if master is None:
            await update.message.reply_text(
                "❌ Профиль мастера не найден.",
                reply_markup=main_menu(),
            )
            return

        day_off = db.scalar(
            select(MasterDayOff).where(
                MasterDayOff.id == day_off_id,
                MasterDayOff.master_id == master.id,
            )
        )

        if day_off is None:
            await update.message.reply_text(
                "❌ Выходной не найден или принадлежит другому мастеру.",
                reply_markup=day_off_menu(),
            )
            return

        selected_date = day_off.day_off_date

        db.delete(day_off)
        db.commit()

        await update.message.reply_text(
            "✅ Выходной удалён.\n\n"
            f"Дата: {selected_date.strftime('%d.%m.%Y')}",
            reply_markup=day_off_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось удалить выходной.",
            reply_markup=day_off_menu(),
        )

    finally:
        db.close()
