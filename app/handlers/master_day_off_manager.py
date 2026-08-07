from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.master_day_off import MasterDayOff
from app.models.salon import Salon
from app.models.user import User
from app.services.timezone import local_today


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}


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
    return db.scalar(
        select(Master)
        .options(
            joinedload(Master.user),
        )
        .join(
            User,
            User.id == Master.user_id,
        )
        .where(
            User.telegram_id == telegram_id
        )
    )


def validate_master(
    master: Master | None,
) -> None:
    if master is None:
        raise ValueError(
            "Профиль мастера не найден."
        )

    if master.user is None or not master.user.is_active:
        raise ValueError(
            "Ваш аккаунт временно отключён."
        )


def master_main_menu(
    db,
    master: Master | None,
    telegram_id: int,
) -> ReplyKeyboardMarkup:
    if master is None or master.user is None:
        return main_menu(
            telegram_id=telegram_id,
        )

    user = master.user

    has_salon = (
        db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=user.role,
        telegram_id=telegram_id,
        has_salon=has_salon,
        has_master=True,
    )


def active_booking_numbers(
    bookings: list[Booking],
) -> str:
    numbers = [
        f"#{booking.id}"
        for booking in bookings[:10]
    ]

    suffix = (
        "…"
        if len(bookings) > 10
        else ""
    )

    return ", ".join(numbers) + suffix


async def open_day_off_panel(
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
        validate_master(master)

        await update.message.reply_text(
            "🏖 Выходные даты мастера\n\n"
            "Здесь можно закрыть целый день для отпуска, "
            "болезни или личных дел.\n\n"
            "Если на дату уже есть активные записи, "
            "сначала их нужно отменить или перенести.",
            reply_markup=day_off_menu(),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                db,
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть выходные даты.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


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
        validate_master(master)

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                db,
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
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

    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
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

    if selected_date < local_today():
        await update.message.reply_text(
            "❌ Нельзя добавить прошедшую дату."
        )
        return True

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )
        validate_master(master)

        existing = db.scalar(
            select(MasterDayOff.id)
            .where(
                MasterDayOff.master_id == master.id,
                MasterDayOff.day_off_date == selected_date,
            )
            .limit(1)
        )

        if existing is not None:
            raise ValueError(
                "Эта дата уже добавлена как выходной."
            )

        active_bookings = list(
            db.scalars(
                select(Booking)
                .where(
                    Booking.master_id == master.id,
                    Booking.booking_date == selected_date,
                    Booking.status.in_(
                        ACTIVE_BOOKING_STATUSES
                    ),
                )
                .order_by(Booking.booking_time)
            ).all()
        )

        if active_bookings:
            raise ValueError(
                "Нельзя поставить выходной: "
                "на эту дату есть активные записи "
                f"{active_booking_numbers(active_bookings)}. "
                "Сначала отмените или перенесите их."
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
        validate_master(master)

        days_off = list(
            db.scalars(
                select(MasterDayOff)
                .where(
                    MasterDayOff.master_id == master.id,
                    MasterDayOff.day_off_date >= local_today(),
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
            reply_markup=day_off_delete_menu(
                days_off
            ),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                db,
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
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
        validate_master(master)

        day_off = db.scalar(
            select(MasterDayOff).where(
                MasterDayOff.id == day_off_id,
                MasterDayOff.master_id == master.id,
            )
        )

        if day_off is None:
            raise ValueError(
                "Выходной не найден или принадлежит другому мастеру."
            )

        selected_date = day_off.day_off_date

        db.delete(day_off)
        db.commit()

        await update.message.reply_text(
            "✅ Выходной удалён.\n\n"
            f"Дата: {selected_date.strftime('%d.%m.%Y')}",
            reply_markup=day_off_menu(),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
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
