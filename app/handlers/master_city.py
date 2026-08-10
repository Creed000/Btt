from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.city import City
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.timezone import local_naive_now


ACTIVE_BOOKING_STATUSES = {
    "new",
    "confirmed",
}

DEFAULT_CITY_NAMES = (
    "Бишкек",
    "Ош",
    "Джалал-Абад",
)


def clear_master_city_selection(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    context.user_data.pop(
        "master_city_selection",
        None,
    )


def get_master(
    db,
    telegram_id: int,
) -> Master | None:
    return db.scalar(
        select(Master)
        .options(
            joinedload(Master.user),
            joinedload(Master.salon),
            joinedload(Master.city),
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


def master_city_menu(
    cities: list[City],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for city in cities:
        keyboard.append(
            [
                KeyboardButton(
                    f"🏙 {city.name}"
                )
            ]
        )

    keyboard.append(
        [KeyboardButton("⬅️ Назад")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите город мастера",
    )


def ensure_default_cities(
    db,
) -> list[City]:
    existing = list(
        db.scalars(
            select(City)
            .where(
                City.is_active.is_(True)
            )
            .order_by(City.name)
        ).all()
    )

    if existing:
        return existing

    for name in DEFAULT_CITY_NAMES:
        city = db.scalar(
            select(City).where(
                City.name == name
            )
        )

        if city is None:
            db.add(
                City(
                    name=name,
                    is_active=True,
                )
            )
        elif not city.is_active:
            city.is_active = True
            db.add(city)

    db.commit()

    return list(
        db.scalars(
            select(City)
            .where(
                City.is_active.is_(True)
            )
            .order_by(City.name)
        ).all()
    )


def get_or_create_active_city(
    db,
    city_name: str,
) -> City:
    """
    Конкурентно-безопасно получает или создаёт город.
    Сравнение нормализовано по регистру и пробелам.
    """
    normalized_name = city_name.strip()

    city = db.scalar(
        select(City)
        .where(
            func.lower(func.trim(City.name))
            == normalized_name.lower()
        )
        .limit(1)
    )

    if city is not None:
        if not city.is_active:
            city.is_active = True
            db.add(city)
            db.flush()
        return city

    try:
        with db.begin_nested():
            city = City(
                name=normalized_name,
                is_active=True,
            )
            db.add(city)
            db.flush()
            city_id = city.id

        return db.get(City, city_id)

    except IntegrityError:
        city = db.scalar(
            select(City)
            .where(
                func.lower(func.trim(City.name))
                == normalized_name.lower()
            )
            .limit(1)
        )

        if city is None:
            raise

        if not city.is_active:
            city.is_active = True
            db.add(city)
            db.flush()

        return city


def has_future_active_bookings(
    db,
    master_id: int,
) -> bool:
    now = local_naive_now()

    bookings = list(
        db.scalars(
            select(Booking).where(
                Booking.master_id == master_id,
                Booking.status.in_(
                    ACTIVE_BOOKING_STATUSES
                ),
            )
        ).all()
    )

    for booking in bookings:
        starts_at = datetime.combine(
            booking.booking_date,
            booking.booking_time,
        )

        if starts_at > now:
            return True

    return False


async def begin_master_city_selection(
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

        if master.salon is not None:
            salon_city_name = (
                master.salon.city or ""
            ).strip()

            if not salon_city_name:
                raise ValueError(
                    "У салона не указан город. "
                    "Сначала владельцу нужно заполнить город салона."
                )

            city = get_or_create_active_city(
                db,
                salon_city_name,
            )

            # create_booking() с шага 336/339 блокирует ту же
            # строку Master. Поэтому смена города не может пройти
            # параллельно с финальным созданием новой записи.
            locked_master = db.scalar(
                select(Master)
                .where(
                    Master.id == master.id
                )
                .with_for_update()
            )

            if locked_master is None:
                raise ValueError(
                    "Профиль мастера больше не существует."
                )

            master = locked_master

            if (
                master.city_id is not None
                and master.city_id != city.id
                and has_future_active_bookings(
                    db,
                    master.id,
                )
            ):
                raise ValueError(
                    "Город салона отличается от города мастера, "
                    "но у вас есть будущие активные записи. "
                    "Сначала завершите, перенесите или отмените их."
                )

            master.city_id = city.id
            db.add(master)
            db.commit()

            clear_master_city_selection(
                context
            )

            await update.message.reply_text(
                "✅ Город мастера синхронизирован с салоном.\n\n"
                f"🏙 Город: {city.name}",
                reply_markup=master_main_menu(
                    db,
                    master,
                    update.effective_user.id,
                ),
            )
            return

        cities = ensure_default_cities(
            db
        )

        clear_master_city_selection(
            context
        )
        context.user_data[
            "master_city_selection"
        ] = True

        current_city = (
            master.city.name
            if master.city is not None
            else "не выбран"
        )

        await update.message.reply_text(
            "🏙 Город мастера\n\n"
            f"Текущий город: {current_city}\n\n"
            "Выберите город, в котором вы принимаете клиентов:",
            reply_markup=master_city_menu(
                cities
            ),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                db,
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось открыть выбор города.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def process_master_city_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if not context.user_data.get(
        "master_city_selection"
    ):
        return False

    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text = update.message.text.strip()

    if text == "⬅️ Назад":
        clear_master_city_selection(
            context
        )

        db = SessionLocal()

        try:
            master = get_master(
                db,
                update.effective_user.id,
            )

            reply_markup = master_main_menu(
                db,
                master,
                update.effective_user.id,
            )
        finally:
            db.close()

        await update.message.reply_text(
            "🏠 Главное меню",
            reply_markup=reply_markup,
        )
        return True

    if not text.startswith("🏙 "):
        await update.message.reply_text(
            "Выберите город с помощью кнопок."
        )
        return True

    city_name = text.removeprefix(
        "🏙 "
    ).strip()

    if not city_name:
        await update.message.reply_text(
            "❌ Не удалось определить город."
        )
        return True

    db = SessionLocal()

    try:
        master = get_master(
            db,
            update.effective_user.id,
        )
        validate_master(master)

        # Синхронизируем смену города с create_booking():
        # после ожидания row-lock все проверки выполняются заново
        # уже на актуальной строке Master.
        locked_master = db.scalar(
            select(Master)
            .where(
                Master.id == master.id
            )
            .with_for_update()
        )

        if locked_master is None:
            raise ValueError(
                "Профиль мастера больше не существует."
            )

        master = locked_master
        validate_master(master)

        if master.salon is not None:
            raise ValueError(
                "Город мастера салона определяется "
                "городом самого салона."
            )

        normalized_city_name = city_name.strip()

        city = db.scalar(
            select(City).where(
                func.lower(func.trim(City.name))
                == normalized_city_name.lower(),
                City.is_active.is_(True),
            )
        )

        if city is None:
            raise ValueError(
                "Этот город больше недоступен. "
                "Откройте выбор города заново."
            )

        if (
            master.city_id == city.id
        ):
            clear_master_city_selection(
                context
            )

            await update.message.reply_text(
                f"ℹ️ Город уже выбран: {city.name}",
                reply_markup=master_main_menu(
                    db,
                    master,
                    update.effective_user.id,
                ),
            )
            return True

        if has_future_active_bookings(
            db,
            master.id,
        ):
            raise ValueError(
                "Нельзя менять город, пока есть будущие "
                "активные записи. Сначала завершите, "
                "перенесите или отмените их."
            )

        master.city_id = city.id
        db.add(master)
        db.commit()
        db.refresh(master)

        clear_master_city_selection(
            context
        )

        await update.message.reply_text(
            f"✅ Город мастера сохранён: {city.name}",
            reply_markup=master_main_menu(
                db,
                master,
                update.effective_user.id,
            ),
        )
        return True

    except ValueError as error:
        db.rollback()
        clear_master_city_selection(
            context
        )

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                db,
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
        )
        return True

    except Exception:
        db.rollback()
        clear_master_city_selection(
            context
        )

        await update.message.reply_text(
            "❌ Не удалось сохранить город мастера.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return True

    finally:
        db.close()
