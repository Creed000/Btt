from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.master_time_block import MasterTimeBlock
from app.models.salon import Salon
from app.models.user import User
from app.services.availability import get_master_working_hours
from app.services.timezone import (
    local_naive_now,
    local_today,
)


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


def intervals_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    return (
        first_start < second_end
        and second_start < first_end
    )


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

    if (
        master.user is None
        or not master.user.is_active
    ):
        raise ValueError(
            "Ваш аккаунт временно отключён."
        )


def master_main_menu(
    db,
    master: Master | None,
    telegram_id: int,
) -> ReplyKeyboardMarkup:
    if (
        master is None
        or master.user is None
    ):
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


def conflicting_booking_numbers(
    bookings: list[Booking],
) -> str:
    values = [
        f"#{booking.id}"
        for booking in bookings[:10]
    ]

    suffix = (
        "…"
        if len(bookings) > 10
        else ""
    )

    return ", ".join(values) + suffix


async def open_time_blocks_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )
        validate_master(master)

        await update.message.reply_text(
            "⏸ Блокировки времени\n\n"
            "Здесь можно закрыть отдельные часы "
            "для обеда, личных дел или временного отсутствия.\n\n"
            "Блокировка должна находиться внутри рабочего "
            "времени и не может пересекать существующие записи.",
            reply_markup=time_blocks_menu(),
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
            "❌ Не удалось открыть блокировки времени.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def begin_time_block_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
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

    clear_time_block_setup(
        context
    )
    context.user_data[
        "time_block_setup"
    ] = "date"

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
    stage = context.user_data.get(
        "time_block_setup"
    )

    if stage is None:
        return False

    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить блокировку времени":
        clear_time_block_setup(
            context
        )

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
                "❌ Нельзя выбрать прошедшую дату."
            )
            return True

        context.user_data[
            "time_block_date"
        ] = block_date
        context.user_data[
            "time_block_setup"
        ] = "start"

        await update.message.reply_text(
            "Шаг 2 из 3. Введите начало блокировки "
            "в формате ЧЧ:ММ.\n\n"
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
                "Введите время в формате ЧЧ:ММ, "
                "например 13:00."
            )
            return True

        context.user_data[
            "time_block_start"
        ] = start_time
        context.user_data[
            "time_block_setup"
        ] = "end"

        await update.message.reply_text(
            "Шаг 3 из 3. Введите окончание блокировки "
            "в формате ЧЧ:ММ.\n\n"
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
                "Введите время в формате ЧЧ:ММ, "
                "например 14:30."
            )
            return True

        block_date = context.user_data.get(
            "time_block_date"
        )
        start_time = context.user_data.get(
            "time_block_start"
        )

        if (
            block_date is None
            or start_time is None
        ):
            clear_time_block_setup(
                context
            )

            await update.message.reply_text(
                "❌ Данные блокировки потеряны. "
                "Начните заново.",
                reply_markup=time_blocks_menu(),
            )
            return True

        if end_time <= start_time:
            await update.message.reply_text(
                "❌ Окончание блокировки должно "
                "быть позже начала."
            )
            return True

        selected_start = datetime.combine(
            block_date,
            start_time,
        )
        selected_end = datetime.combine(
            block_date,
            end_time,
        )

        if selected_start <= local_naive_now():
            await update.message.reply_text(
                "❌ Начало блокировки должно быть "
                "в будущем."
            )
            return True

        if (
            selected_end - selected_start
            < timedelta(minutes=15)
        ):
            await update.message.reply_text(
                "❌ Блокировка должна длиться "
                "минимум 15 минут."
            )
            return True

        db = SessionLocal()

        try:
            master = get_master(
                db,
                update.effective_user.id,
            )
            validate_master(master)

            working_hours = get_master_working_hours(
                db,
                master.id,
                block_date,
            )

            if working_hours is None:
                raise ValueError(
                    "На выбранную дату мастер не работает "
                    "или дата отмечена выходной."
                )

            work_start, work_end = (
                working_hours
            )

            work_start_dt = datetime.combine(
                block_date,
                work_start,
            )
            work_end_dt = datetime.combine(
                block_date,
                work_end,
            )

            if (
                selected_start < work_start_dt
                or selected_end > work_end_dt
            ):
                raise ValueError(
                    "Блокировка должна полностью находиться "
                    "внутри рабочего времени: "
                    f"{work_start.strftime('%H:%M')}–"
                    f"{work_end.strftime('%H:%M')}."
                )

            existing_blocks = list(
                db.scalars(
                    select(MasterTimeBlock)
                    .where(
                        MasterTimeBlock.master_id
                        == master.id,
                        MasterTimeBlock.block_date
                        == block_date,
                    )
                    .order_by(
                        MasterTimeBlock.start_time
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
                        "Новая блокировка пересекается "
                        "с существующей."
                    )

            bookings = list(
                db.scalars(
                    select(Booking)
                    .options(
                        joinedload(
                            Booking.service
                        )
                    )
                    .where(
                        Booking.master_id == master.id,
                        Booking.booking_date == block_date,
                        Booking.status.in_(
                            ACTIVE_BOOKING_STATUSES
                        ),
                    )
                    .order_by(
                        Booking.booking_time
                    )
                ).unique().all()
            )

            conflicting_bookings: list[
                Booking
            ] = []

            for booking in bookings:
                duration = (
                    booking.service.duration
                    if booking.service is not None
                    else 30
                )

                booking_start = datetime.combine(
                    booking.booking_date,
                    booking.booking_time,
                )

                booking_end = (
                    booking_start
                    + timedelta(
                        minutes=duration
                    )
                )

                if intervals_overlap(
                    selected_start,
                    selected_end,
                    booking_start,
                    booking_end,
                ):
                    conflicting_bookings.append(
                        booking
                    )

            if conflicting_bookings:
                raise ValueError(
                    "Нельзя создать блокировку: "
                    "она пересекается с активными "
                    f"записями "
                    f"{conflicting_booking_numbers(conflicting_bookings)}."
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
            clear_time_block_setup(
                context
            )

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=time_blocks_menu(),
            )
            return True

        except Exception:
            db.rollback()
            clear_time_block_setup(
                context
            )

            await update.message.reply_text(
                "❌ Не удалось сохранить блокировку.",
                reply_markup=time_blocks_menu(),
            )
            return True

        finally:
            db.close()

        clear_time_block_setup(
            context
        )

        await update.message.reply_text(
            "✅ Блокировка времени добавлена!\n\n"
            f"Дата: "
            f"{block_date.strftime('%d.%m.%Y')}\n"
            f"Время: "
            f"{start_time.strftime('%H:%M')}–"
            f"{end_time.strftime('%H:%M')}",
            reply_markup=time_blocks_menu(),
        )
        return True

    return False


async def show_master_time_blocks(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )
        validate_master(master)

        blocks = list(
            db.scalars(
                select(MasterTimeBlock)
                .where(
                    MasterTimeBlock.master_id
                    == master.id,
                    MasterTimeBlock.block_date
                    >= local_today(),
                )
                .order_by(
                    MasterTimeBlock.block_date,
                    MasterTimeBlock.start_time,
                )
            ).all()
        )

        lines = [
            "📋 Мои блокировки времени"
        ]

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
                    if getattr(
                        block,
                        "reason",
                        None,
                    )
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
            reply_markup=time_blocks_delete_menu(
                blocks
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
            "❌ Не удалось загрузить блокировки.",
            reply_markup=time_blocks_menu(),
        )

    finally:
        db.close()


async def delete_master_time_block(
    update: Update,
    block_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )
        validate_master(master)

        block = db.scalar(
            select(MasterTimeBlock).where(
                MasterTimeBlock.id == block_id,
                MasterTimeBlock.master_id
                == master.id,
            )
        )

        if block is None:
            raise ValueError(
                "Блокировка не найдена или "
                "принадлежит другому мастеру."
            )

        block_date = block.block_date
        start_time = block.start_time
        end_time = block.end_time

        db.delete(block)
        db.commit()

        await update.message.reply_text(
            "✅ Блокировка удалена.\n\n"
            f"Дата: "
            f"{block_date.strftime('%d.%m.%Y')}\n"
            f"Время: "
            f"{start_time.strftime('%H:%M')}–"
            f"{end_time.strftime('%H:%M')}",
            reply_markup=time_blocks_menu(),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
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
