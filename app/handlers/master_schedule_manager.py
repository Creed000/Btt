from datetime import date, datetime, timedelta

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.master_schedule import MasterSchedule
from app.models.service import Service
from app.models.user import User


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}

WEEKDAYS = {
    "📅 Понедельник": 0,
    "📅 Вторник": 1,
    "📅 Среда": 2,
    "📅 Четверг": 3,
    "📅 Пятница": 4,
    "📅 Суббота": 5,
    "📅 Воскресенье": 6,
}

WEEKDAY_NAMES = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def schedule_overview_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("⚙️ Настроить расписание")],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Расписание мастера",
    )


def schedule_weekday_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📅 Понедельник")],
            [KeyboardButton("📅 Вторник")],
            [KeyboardButton("📅 Среда")],
            [KeyboardButton("📅 Четверг")],
            [KeyboardButton("📅 Пятница")],
            [KeyboardButton("📅 Суббота")],
            [KeyboardButton("📅 Воскресенье")],
            [KeyboardButton("❌ Отменить настройку расписания")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите день недели",
    )


def schedule_mode_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🕘 Настроить рабочее время")],
            [KeyboardButton("🚫 Сделать выходным")],
            [KeyboardButton("❌ Отменить настройку расписания")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите режим дня",
    )


def clear_schedule_setup(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "schedule_setup",
        "schedule_weekday",
        "schedule_start",
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


def get_conflicting_bookings(
    db,
    master_id: int,
    weekday: int,
    work_start=None,
    work_end=None,
    make_day_off: bool = False,
    days_ahead: int = 90,
) -> list[Booking]:
    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    bookings = list(
        db.scalars(
            select(Booking)
            .where(
                Booking.master_id == master_id,
                Booking.booking_date >= today,
                Booking.booking_date <= end_date,
                Booking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
            .order_by(
                Booking.booking_date,
                Booking.booking_time,
            )
        ).all()
    )

    conflicts: list[Booking] = []

    for booking in bookings:
        if booking.booking_date.weekday() != weekday:
            continue

        if make_day_off:
            conflicts.append(booking)
            continue

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

        booking_end = booking_start + timedelta(
            minutes=duration
        )

        schedule_start = datetime.combine(
            booking.booking_date,
            work_start,
        )

        schedule_end = datetime.combine(
            booking.booking_date,
            work_end,
        )

        if (
            booking_start < schedule_start
            or booking_end > schedule_end
        ):
            conflicts.append(booking)

    return conflicts


async def show_master_schedule(
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

        schedules = list(
            db.scalars(
                select(MasterSchedule)
                .where(
                    MasterSchedule.master_id == master.id
                )
                .order_by(MasterSchedule.weekday)
            ).all()
        )

        schedule_map = {
            item.weekday: item
            for item in schedules
        }

        lines = [
            "🗓 Моё расписание",
            "",
        ]

        for weekday in range(7):
            schedule = schedule_map.get(weekday)
            day_name = WEEKDAY_NAMES[weekday]

            if schedule is None:
                lines.append(
                    f"{day_name}: 09:00–18:00 (по умолчанию)"
                )
            elif not schedule.is_working:
                lines.append(
                    f"{day_name}: выходной"
                )
            else:
                lines.append(
                    f"{day_name}: "
                    f"{schedule.work_start.strftime('%H:%M')}–"
                    f"{schedule.work_end.strftime('%H:%M')}"
                )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=schedule_overview_menu(),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить расписание.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def begin_schedule_setup(
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

    clear_schedule_setup(context)
    context.user_data["schedule_setup"] = "weekday"

    await update.message.reply_text(
        "⚙️ Настройка расписания\n\n"
        "Выберите день недели:",
        reply_markup=schedule_weekday_menu(),
    )


async def process_schedule_setup(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("schedule_setup")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить настройку расписания":
        clear_schedule_setup(context)
        await show_master_schedule(update, context)
        return True

    if stage == "weekday":
        weekday = WEEKDAYS.get(text)

        if weekday is None:
            await update.message.reply_text(
                "Выберите день недели с помощью кнопок."
            )
            return True

        context.user_data["schedule_weekday"] = weekday
        context.user_data["schedule_setup"] = "mode"

        await update.message.reply_text(
            f"Выбран день: {WEEKDAY_NAMES[weekday]}\n\n"
            "Выберите режим:",
            reply_markup=schedule_mode_menu(),
        )
        return True

    if stage == "mode":
        weekday = context.user_data.get("schedule_weekday")

        if weekday is None:
            clear_schedule_setup(context)
            await update.message.reply_text(
                "❌ День недели не выбран.",
                reply_markup=main_menu(),
            )
            return True

        if text == "🚫 Сделать выходным":
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

                conflicts = get_conflicting_bookings(
                    db,
                    master.id,
                    weekday,
                    make_day_off=True,
                )

                if conflicts:
                    numbers = ", ".join(
                        f"#{booking.id}"
                        for booking in conflicts[:10]
                    )

                    raise ValueError(
                        "Нельзя сделать день выходным: "
                        f"есть активные записи {numbers}. "
                        "Сначала отмените или перенесите их."
                    )

                schedule = db.scalar(
                    select(MasterSchedule).where(
                        MasterSchedule.master_id == master.id,
                        MasterSchedule.weekday == weekday,
                    )
                )

                if schedule is None:
                    schedule = MasterSchedule(
                        master_id=master.id,
                        weekday=weekday,
                        is_working=False,
                    )
                    db.add(schedule)
                else:
                    schedule.is_working = False

                db.commit()

            except ValueError as error:
                db.rollback()
                clear_schedule_setup(context)

                await update.message.reply_text(
                    f"❌ {error}",
                    reply_markup=schedule_overview_menu(),
                )
                return True

            except Exception:
                db.rollback()
                clear_schedule_setup(context)

                await update.message.reply_text(
                    "❌ Не удалось сохранить выходной день.",
                    reply_markup=main_menu(),
                )
                return True

            finally:
                db.close()

            clear_schedule_setup(context)

            await update.message.reply_text(
                f"✅ {WEEKDAY_NAMES[weekday]} отмечен как выходной."
            )
            await show_master_schedule(update, context)
            return True

        if text == "🕘 Настроить рабочее время":
            context.user_data["schedule_setup"] = "start"

            await update.message.reply_text(
                "Введите начало работы в формате ЧЧ:ММ.\n\n"
                "Например: 09:00"
            )
            return True

        await update.message.reply_text(
            "Выберите режим дня с помощью кнопок."
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
                "Введите время в формате ЧЧ:ММ, например 09:00."
            )
            return True

        context.user_data["schedule_start"] = start_time
        context.user_data["schedule_setup"] = "end"

        await update.message.reply_text(
            "Введите окончание работы в формате ЧЧ:ММ.\n\n"
            "Например: 18:00"
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
                "Введите время в формате ЧЧ:ММ, например 18:00."
            )
            return True

        start_time = context.user_data.get("schedule_start")
        weekday = context.user_data.get("schedule_weekday")

        if start_time is None or weekday is None:
            clear_schedule_setup(context)

            await update.message.reply_text(
                "❌ Данные расписания потеряны. Начните заново.",
                reply_markup=main_menu(),
            )
            return True

        if end_time <= start_time:
            await update.message.reply_text(
                "Время окончания должно быть позже начала."
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

            conflicts = get_conflicting_bookings(
                db,
                master.id,
                weekday,
                work_start=start_time,
                work_end=end_time,
            )

            if conflicts:
                numbers = ", ".join(
                    f"#{booking.id}"
                    for booking in conflicts[:10]
                )

                raise ValueError(
                    "Нельзя сохранить новый график: "
                    f"записи {numbers} находятся вне выбранного времени. "
                    "Сначала отмените или перенесите их."
                )

            schedule = db.scalar(
                select(MasterSchedule).where(
                    MasterSchedule.master_id == master.id,
                    MasterSchedule.weekday == weekday,
                )
            )

            if schedule is None:
                schedule = MasterSchedule(
                    master_id=master.id,
                    weekday=weekday,
                    work_start=start_time,
                    work_end=end_time,
                    is_working=True,
                )
                db.add(schedule)
            else:
                schedule.work_start = start_time
                schedule.work_end = end_time
                schedule.is_working = True

            db.commit()

        except ValueError as error:
            db.rollback()
            clear_schedule_setup(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=schedule_overview_menu(),
            )
            return True

        except Exception:
            db.rollback()
            clear_schedule_setup(context)

            await update.message.reply_text(
                "❌ Не удалось сохранить расписание.",
                reply_markup=main_menu(),
            )
            return True

        finally:
            db.close()

        clear_schedule_setup(context)

        await update.message.reply_text(
            "✅ Расписание сохранено!"
        )
        await show_master_schedule(update, context)
        return True

    return False
