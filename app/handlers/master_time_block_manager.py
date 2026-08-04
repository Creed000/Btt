from datetime import date, datetime

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.master_time_block import MasterTimeBlock
from app.models.service import Service
from app.models.user import User
from app.services.timezone import local_today


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}


def time_blocks_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("➕ Добавить блокировку времени")],
            [KeyboardButton("📋 Мои блокировки времени")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Блокировки времени",
    )


def time_block_cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("❌ Отменить блокировку времени")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите данные блокировки",
    )


def time_blocks_delete_menu(
    blocks: list[MasterTimeBlock],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for block in blocks:
        keyboard.append(
            [
                KeyboardButton(
                    f"🗑 Удалить блокировку #{block.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("➕ Добавить блокировку времени")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление блокировками",
    )


def clear_time_block_setup(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "time_block_setup",
        "time_block_date",
        "time_block_start",
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


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return first_start < second_end and second_start < first_end


async def open_time_blocks_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    await update.message.reply_text(
        "⏸ Блокировки времени\n\n"
        "Здесь можно закрыть отдельные часы для обеда, "
        "личных дел или временного отсутствия.",
        reply_markup=time_blocks_menu(),
    )


async def begin_time_block_creation(
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

    clear_time_block_setup(context)
    context.user_data["time_block_setup"] = "date"

    await update.message.reply_text(
        "➕ Новая блокировка времени\n\n"
        "Шаг 1 из 3. Введите дату в формате ДД.ММ.ГГГГ.\n\n"
        "Например: 15.08.2026",
        reply_markup=time_block_cancel_menu(),
    )


async def process_time_block_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("time_block_setup")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить блокировку времени":
        clear_time_block_setup(context)

        await update.message.reply_text(
            "❌ Добавление блокировки отменено.",
            reply_markup=time_blocks_menu(),
        )
        return True

    if stage == "date":
        try:
            block_date = datetime.strptime(
                text,
                "%d.%m.%Y",
            ).date()
        except ValueError:
            await update.message.reply_text(
                "Введите дату в формате ДД.ММ.ГГГГ.\n"
                "Например: 15.08.2026"
            )
            return True

        if block_date < local_today():
            await update.message.reply_text(
                "Нельзя выбрать прошедшую дату."
            )
            return True

        context.user_data["time_block_date"] = block_date
        context.user_data["time_block_setup"] = "start"

        await update.message.reply_text(
            "Шаг 2 из 3. Введите начало блокировки в формате ЧЧ:ММ.\n\n"
            "Например: 13:00"
        )
        return True

    if stage == "start":
        try:
            start_time = datetime.strptime(
                text,
                "%H:%M",
            ).time()
        except ValueError:
            await update.message.reply_text(
                "Введите время в формате ЧЧ:ММ, например 13:00."
            )
            return True

        context.user_data["time_block_start"] = start_time
        context.user_data["time_block_setup"] = "end"

        await update.message.reply_text(
            "Шаг 3 из 3. Введите окончание блокировки в формате ЧЧ:ММ.\n\n"
            "Например: 14:30"
        )
        return True

    if stage == "end":
        try:
            end_time = datetime.strptime(
                text,
                "%H:%M",
            ).time()
        except ValueError:
            await update.message.reply_text(
                "Введите время в формате ЧЧ:ММ, например 14:30."
            )
            return True

        block_date = context.user_data.get("time_block_date")
        start_time = context.user_data.get("time_block_start")

        if block_date is None or start_time is None:
            clear_time_block_setup(context)

            await update.message.reply_text(
                "❌ Данные блокировки потеряны. Начните заново.",
                reply_markup=time_blocks_menu(),
            )
            return True

        if end_time <= start_time:
            await update.message.reply_text(
                "Окончание блокировки должно быть позже начала."
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

            selected_start = datetime.combine(
                block_date,
                start_time,
            )

            selected_end = datetime.combine(
                block_date,
                end_time,
            )

            existing_blocks = list(
                db.scalars(
                    select(MasterTimeBlock).where(
                        MasterTimeBlock.master_id == master.id,
                        MasterTimeBlock.block_date == block_date,
                    )
                ).all()
            )

            for block in existing_blocks:
                existing_start = datetime.combine(
                    block.block_date,
                    block.start_time,
                )
                existing_end = datetime.combine(
                    block.block_date,
                    block.end_time,
                )

                if intervals_overlap(
                    selected_start,
                    selected_end,
                    existing_start,
                    existing_end,
                ):
                    raise ValueError(
                        "Новая блокировка пересекается с существующей."
                    )

            bookings = list(
                db.scalars(
                    select(Booking).where(
                        Booking.master_id == master.id,
                        Booking.booking_date == block_date,
                        Booking.status.in_(
                            ACTIVE_BOOKING_STATUSES
                        ),
                    )
                ).all()
            )

            conflicting_bookings: list[Booking] = []

            for booking in bookings:
                service = db.scalar(
                    select(Service).where(
                        Service.id == booking.service_id
                    )
                )

                duration = (
                    service.duration
                    if service is not None
                    else 30
                )

                booking_start = datetime.combine(
                    booking.booking_date,
                    booking.booking_time,
                )

                booking_end = booking_start + __import__(
                    "datetime"
                ).timedelta(minutes=duration)

                if intervals_overlap(
                    selected_start,
                    selected_end,
                    booking_start,
                    booking_end,
                ):
                    conflicting_bookings.append(booking)

            if conflicting_bookings:
                numbers = ", ".join(
                    f"#{booking.id}"
                    for booking in conflicting_bookings[:10]
                )

                raise ValueError(
                    "Нельзя создать блокировку: "
                    f"есть активные записи {numbers}."
                )

            block = MasterTimeBlock(
                master_id=master.id,
                block_date=block_date,
                start_time=start_time,
                end_time=end_time,
            )

            db.add(block)
            db.commit()

        except ValueError as error:
            db.rollback()
            clear_time_block_setup(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=time_blocks_menu(),
            )
            return True

        except Exception:
            db.rollback()
            clear_time_block_setup(context)

            await update.message.reply_text(
                "❌ Не удалось сохранить блокировку.",
                reply_markup=time_blocks_menu(),
            )
            return True

        finally:
            db.close()

        clear_time_block_setup(context)

        await update.message.reply_text(
            "✅ Блокировка времени добавлена!\n\n"
            f"Дата: {block_date.strftime('%d.%m.%Y')}\n"
            f"Время: {start_time.strftime('%H:%M')}–"
            f"{end_time.strftime('%H:%M')}",
            reply_markup=time_blocks_menu(),
        )
        return True

    return False


async def show_master_time_blocks(
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

        blocks = list(
            db.scalars(
                select(MasterTimeBlock)
                .where(
                    MasterTimeBlock.master_id == master.id,
                    MasterTimeBlock.block_date >= local_today(),
                )
                .order_by(
                    MasterTimeBlock.block_date,
                    MasterTimeBlock.start_time,
                )
            ).all()
        )

        lines = ["📋 Мои блокировки времени"]

        if not blocks:
            lines.extend(
                [
                    "",
                    "Будущих блокировок пока нет.",
                ]
            )
        else:
            for block in blocks:
                reason = (
                    f" — {block.reason}"
                    if block.reason
                    else ""
                )

                lines.append(
                    f"#{block.id} · "
                    f"{block.block_date.strftime('%d.%m.%Y')} · "
                    f"{block.start_time.strftime('%H:%M')}–"
                    f"{block.end_time.strftime('%H:%M')}"
                    f"{reason}"
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=time_blocks_delete_menu(blocks),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить блокировки.",
            reply_markup=time_blocks_menu(),
        )

    finally:
        db.close()


async def delete_master_time_block(
    update: Update,
    block_id: int,
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

        block = db.scalar(
            select(MasterTimeBlock).where(
                MasterTimeBlock.id == block_id,
                MasterTimeBlock.master_id == master.id,
            )
        )

        if block is None:
            await update.message.reply_text(
                "❌ Блокировка не найдена или принадлежит другому мастеру.",
                reply_markup=time_blocks_menu(),
            )
            return

        block_date = block.block_date
        start_time = block.start_time
        end_time = block.end_time

        db.delete(block)
        db.commit()

        await update.message.reply_text(
            "✅ Блокировка удалена.\n\n"
            f"Дата: {block_date.strftime('%d.%m.%Y')}\n"
            f"Время: {start_time.strftime('%H:%M')}–"
            f"{end_time.strftime('%H:%M')}",
            reply_markup=time_blocks_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось удалить блокировку.",
            reply_markup=time_blocks_menu(),
        )

    finally:
        db.close()
