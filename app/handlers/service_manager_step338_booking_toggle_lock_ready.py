from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.branch import Branch
from app.models.category import Category
from app.models.master import Master
from app.models.master_schedule import MasterSchedule
from app.models.salon import Salon
from app.models.service import Service
from app.models.user import User
from app.services.subscription_access import require_active_salon_access
from app.services.subscription_limits import can_enable_master


CATEGORY_BUTTONS = {
    "💇 Волосы": ("Волосы", "💇"),
    "💅 Маникюр": ("Маникюр", "💅"),
    "👁 Ресницы": ("Ресницы", "👁"),
    "💆 Массаж": ("Массаж", "💆"),
}


def service_category_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("💇 Волосы")],
            [KeyboardButton("💅 Маникюр")],
            [KeyboardButton("👁 Ресницы")],
            [KeyboardButton("💆 Массаж")],
            [KeyboardButton("❌ Отменить добавление услуги")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите категорию",
    )


def master_actions_menu(
    booking_enabled: bool,
) -> ReplyKeyboardMarkup:
    booking_button = (
        "⛔ Выключить запись"
        if booking_enabled
        else "✅ Включить запись"
    )

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📅 Мои записи")],
            [KeyboardButton("🗓 Моё расписание")],
            [KeyboardButton("🏖 Выходные даты")],
            [KeyboardButton("⏸ Блокировки времени")],
            [KeyboardButton("➕ Добавить услугу")],
            [KeyboardButton("📋 Мои услуги")],
            [KeyboardButton("🏙 Мой город")],
            [KeyboardButton(booking_button)],
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Кабинет мастера",
    )


def services_list_menu(
    services: list[Service],
    booking_enabled: bool,
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for service in services:
        keyboard.append(
            [
                KeyboardButton(
                    f"🗑 Удалить услугу #{service.id}"
                )
            ]
        )

    keyboard.extend(
        [
            [KeyboardButton("➕ Добавить услугу")],
            [
                KeyboardButton(
                    "⛔ Выключить запись"
                    if booking_enabled
                    else "✅ Включить запись"
                )
            ],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление услугами",
    )


def cancel_service_creation(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "service_creation",
        "service_category_name",
        "service_category_icon",
        "service_title",
        "service_duration",
    ):
        context.user_data.pop(key, None)


def get_current_user(
    db,
    telegram_id: int,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )


def get_current_master(
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
        .join(User, User.id == Master.user_id)
        .where(
            User.telegram_id == telegram_id
        )
    )


def master_main_menu(
    master: Master | None,
    telegram_id: int,
) -> ReplyKeyboardMarkup:
    user = (
        master.user
        if master is not None
        else None
    )

    return main_menu(
        role=user.role if user else None,
        telegram_id=telegram_id,
        has_master=master is not None,
        has_salon=(
            bool(master and master.salon)
            if user and user.role == "owner"
            else None
        ),
    )


def validate_master_can_manage(
    master: Master | None,
) -> None:
    if master is None:
        raise ValueError(
            "Профиль мастера не найден. "
            "Сначала откройте «💼 Стать мастером»."
        )

    if master.user is None or not master.user.is_active:
        raise ValueError(
            "Ваш аккаунт временно отключён."
        )



def get_or_create_category(
    db,
    category_name: str,
    category_icon: str | None,
) -> Category:
    """
    Конкурентно-безопасный get-or-create.

    SAVEPOINT позволяет пережить уникальный конфликт,
    не откатывая всю транзакцию создания услуги.
    """
    normalized_name = category_name.strip()

    category = db.scalar(
        select(Category)
        .where(
            func.lower(func.trim(Category.name))
            == normalized_name.lower()
        )
        .limit(1)
    )

    if category is not None:
        return category

    try:
        with db.begin_nested():
            category = Category(
                name=normalized_name,
                icon=category_icon,
            )
            db.add(category)
            db.flush()
            category_id = category.id

        return db.get(Category, category_id)

    except IntegrityError:
        # Другая Railway-реплика успела создать
        # эту категорию между SELECT и INSERT.
        category = db.scalar(
            select(Category)
            .where(
                func.lower(func.trim(Category.name))
                == normalized_name.lower()
            )
            .limit(1)
        )

        if category is None:
            raise

        return category


def validate_booking_readiness(
    db,
    master: Master,
) -> None:
    """
    Проверка перед включением booking_enabled.

    Критерии синхронизированы с единым каталогом:
    мастер не должен суметь включить запись в состоянии,
    в котором клиент всё равно не увидит его в поиске.
    """
    validate_master_can_manage(master)

    if not master.is_verified:
        raise ValueError(
            "Профиль мастера ещё не подтверждён администратором."
        )

    if master.city_id is None:
        raise ValueError(
            "Сначала выберите город в разделе «🏙 Мой город»."
        )

    if (
        master.city is None
        or not master.city.is_active
    ):
        raise ValueError(
            "Выбранный город сейчас недоступен. "
            "Выберите другой город."
        )

    valid_services_count = (
        db.scalar(
            select(
                func.count(Service.id)
            )
            .join(
                Category,
                Category.id == Service.category_id,
            )
            .where(
                Service.master_id == master.id,
                Service.category_id.is_not(None),
                Service.duration > 0,
                Service.price >= 0,
            )
        )
        or 0
    )

    if valid_services_count < 1:
        raise ValueError(
            "Сначала добавьте хотя бы одну корректную услугу "
            "с категорией, ценой и длительностью."
        )

    configured_days = (
        db.scalar(
            select(
                func.count(
                    func.distinct(
                        MasterSchedule.weekday
                    )
                )
            ).where(
                MasterSchedule.master_id == master.id,
                MasterSchedule.weekday.between(0, 6),
            )
        )
        or 0
    )

    if configured_days < 7:
        raise ValueError(
            "Сначала настройте всю неделю в разделе "
            "«🗓 Моё расписание»: каждый из 7 дней "
            "должен быть отмечен как рабочий или выходной."
        )

    valid_working_days = (
        db.scalar(
            select(
                func.count(
                    MasterSchedule.id
                )
            ).where(
                MasterSchedule.master_id == master.id,
                MasterSchedule.is_working.is_(True),
                MasterSchedule.weekday.between(0, 6),
                MasterSchedule.work_start.is_not(None),
                MasterSchedule.work_end.is_not(None),
                MasterSchedule.work_start
                < MasterSchedule.work_end,
            )
        )
        or 0
    )

    if valid_working_days < 1:
        raise ValueError(
            "Нельзя включить запись, если нет ни одного "
            "корректного рабочего дня. Проверьте часы "
            "начала и окончания работы."
        )

    if master.salon is not None:
        require_active_salon_access(
            master.salon
        )

        if master.branch_id is None:
            raise ValueError(
                "Владелец салона ещё не назначил вам филиал."
            )

        branch_exists = db.scalar(
            select(Branch.id)
            .where(
                Branch.id == master.branch_id,
                Branch.salon_id
                == master.salon_id,
            )
            .limit(1)
        )

        if branch_exists is None:
            raise ValueError(
                "Назначенный филиал больше не относится "
                "к вашему салону. Попросите владельца "
                "назначить филиал заново."
            )

        allowed, reason = can_enable_master(
            db,
            master.salon,
            master,
        )

        if not allowed:
            raise ValueError(reason)


async def begin_add_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_current_master(
            db,
            update.effective_user.id,
        )

        validate_master_can_manage(
            master
        )

        if master.salon is not None:
            require_active_salon_access(
                master.salon
            )

        cancel_service_creation(context)
        context.user_data[
            "service_creation"
        ] = "category"

        await update.message.reply_text(
            "➕ Добавление услуги\n\n"
            "Шаг 1 из 4. Выберите категорию:",
            reply_markup=service_category_menu(),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def show_master_services(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_current_master(
            db,
            update.effective_user.id,
        )

        validate_master_can_manage(
            master
        )

        services = list(
            db.scalars(
                select(Service)
                .options(
                    joinedload(Service.category)
                )
                .where(
                    Service.master_id == master.id
                )
                .order_by(Service.id)
            ).all()
        )

        if not services:
            await update.message.reply_text(
                "📋 Мои услуги\n\n"
                "У вас пока нет добавленных услуг.",
                reply_markup=master_actions_menu(
                    master.booking_enabled
                ),
            )
            return

        lines = ["📋 Мои услуги"]

        for service in services:
            category_name = (
                service.category.name
                if service.category
                else "Без категории"
            )

            lines.extend(
                [
                    "",
                    f"№{service.id}",
                    f"💼 {service.title}",
                    f"📂 Категория: {category_name}",
                    f"⏱ Длительность: {service.duration} мин.",
                    f"💰 Цена: {service.price} сом",
                ]
            )

        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=services_list_menu(
                services,
                master.booking_enabled,
            ),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=master_main_menu(
                master if "master" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить услуги. Попробуйте позже.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def delete_master_service(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_current_master(
            db,
            update.effective_user.id,
        )

        validate_master_can_manage(
            master
        )

        # create_booking() с шага 336 блокирует ту же строку Master.
        # Поэтому удаление услуги и создание новой записи по этой
        # услуге не могут пройти критические проверки одновременно.
        locked_master_id = db.scalar(
            select(Master.id)
            .where(
                Master.id == master.id
            )
            .with_for_update()
        )

        if locked_master_id is None:
            raise ValueError(
                "Профиль мастера больше не существует."
            )

        service = db.scalar(
            select(Service).where(
                Service.id == service_id,
                Service.master_id == master.id,
            )
        )

        if service is None:
            raise ValueError(
                "Услуга не найдена или принадлежит другому мастеру."
            )

        booking_exists = db.scalar(
            select(Booking.id)
            .where(
                Booking.service_id == service.id
            )
            .limit(1)
        )

        if booking_exists is not None:
            raise ValueError(
                "Эту услугу нельзя удалить, потому что по ней "
                "уже есть записи. Она нужна для сохранения истории."
            )

        service_title = service.title

        db.delete(service)
        db.commit()

        await update.message.reply_text(
            f"✅ Услуга «{service_title}» удалена.",
            reply_markup=master_actions_menu(
                master.booking_enabled
            ),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=(
                master_actions_menu(
                    master.booking_enabled
                )
                if "master" in locals()
                and master is not None
                else main_menu(
                    telegram_id=update.effective_user.id,
                )
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось удалить услугу.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def toggle_master_booking(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    enabled: bool,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        master = get_current_master(
            db,
            update.effective_user.id,
        )

        validate_master_can_manage(
            master
        )

        locked_salon = None

        # Сохраняем единый порядок блокировок для салонных мастеров:
        # Salon -> Master. Это совместимо с лимитами тарифа и снижает
        # риск deadlock с другими salon-flow.
        if enabled and master.salon_id is not None:
            locked_salon = db.scalar(
                select(Salon)
                .where(
                    Salon.id == master.salon_id,
                    Salon.is_active.is_(True),
                )
                .with_for_update()
            )

            if locked_salon is None:
                raise ValueError(
                    "Салон больше недоступен."
                )

        # create_booking() с шага 336 берёт тот же Master FOR UPDATE.
        # Поэтому включение/выключение приёма и финальное создание
        # новой записи теперь сериализованы одной строкой мастера.
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

        if locked_salon is not None:
            master.salon = locked_salon

        # После ожидания row-lock повторно проверяем актуальное состояние
        # аккаунта и readiness, а не используем данные до блокировки.
        validate_master_can_manage(
            master
        )

        if enabled:
            validate_booking_readiness(
                db,
                master,
            )

        if master.booking_enabled == enabled:
            status_text = (
                "ℹ️ Приём записей уже включён."
                if enabled
                else "ℹ️ Приём записей уже выключен."
            )

            await update.message.reply_text(
                status_text,
                reply_markup=master_actions_menu(
                    master.booking_enabled
                ),
            )
            return

        master.booking_enabled = enabled
        db.add(master)
        db.commit()
        db.refresh(master)

        status_text = (
            "✅ Приём записей включён."
            if enabled
            else "⛔ Приём записей выключен."
        )

        await update.message.reply_text(
            status_text,
            reply_markup=master_actions_menu(
                master.booking_enabled
            ),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ Приём записей не включён.\n\n{error}"
            if enabled
            else f"❌ {error}",
            reply_markup=(
                master_actions_menu(
                    master.booking_enabled
                )
                if "master" in locals()
                and master is not None
                else main_menu(
                    telegram_id=update.effective_user.id,
                )
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус записи.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def process_service_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    stage = context.user_data.get(
        "service_creation"
    )

    if stage is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить добавление услуги":
        cancel_service_creation(context)

        db = SessionLocal()

        try:
            master = get_current_master(
                db,
                update.effective_user.id,
            )

            reply_markup = (
                master_actions_menu(
                    master.booking_enabled
                )
                if master is not None
                else main_menu(
                    telegram_id=update.effective_user.id,
                )
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Добавление услуги отменено.",
            reply_markup=reply_markup,
        )
        return True

    if stage == "category":
        category_data = CATEGORY_BUTTONS.get(
            text
        )

        if category_data is None:
            await update.message.reply_text(
                "Выберите категорию с помощью кнопок."
            )
            return True

        category_name, category_icon = (
            category_data
        )

        context.user_data[
            "service_category_name"
        ] = category_name
        context.user_data[
            "service_category_icon"
        ] = category_icon
        context.user_data[
            "service_creation"
        ] = "title"

        await update.message.reply_text(
            "Шаг 2 из 4. Введите название услуги.\n\n"
            "Например: Классическое наращивание"
        )
        return True

    if stage == "title":
        normalized_title = text.strip()

        if len(normalized_title) < 2 or len(normalized_title) > 100:
            await update.message.reply_text(
                "Название должно содержать от 2 до 100 символов."
            )
            return True

        context.user_data[
            "service_title"
        ] = normalized_title
        context.user_data[
            "service_creation"
        ] = "duration"

        await update.message.reply_text(
            "Шаг 3 из 4. Введите длительность услуги "
            "в минутах.\n\nНапример: 120"
        )
        return True

    if stage == "duration":
        try:
            duration = int(text)
        except ValueError:
            await update.message.reply_text(
                "Введите длительность целым числом, например: 120"
            )
            return True

        if duration < 15 or duration > 720:
            await update.message.reply_text(
                "Длительность должна быть от 15 до 720 минут."
            )
            return True

        context.user_data[
            "service_duration"
        ] = duration
        context.user_data[
            "service_creation"
        ] = "price"

        await update.message.reply_text(
            "Шаг 4 из 4. Введите цену услуги "
            "целым числом.\n\nНапример: 2500"
        )
        return True

    if stage == "price":
        try:
            price = int(text)
        except ValueError:
            await update.message.reply_text(
                "Введите цену целым числом, например: 2500"
            )
            return True

        if price < 0 or price > 10_000_000:
            await update.message.reply_text(
                "Цена должна быть от 0 до 10 000 000."
            )
            return True

        db = SessionLocal()

        try:
            master = get_current_master(
                db,
                update.effective_user.id,
            )

            validate_master_can_manage(
                master
            )

            if master.salon is not None:
                require_active_salon_access(
                    master.salon
                )

            category_name = context.user_data.get(
                "service_category_name"
            )
            category_icon = context.user_data.get(
                "service_category_icon"
            )
            service_title = context.user_data.get(
                "service_title"
            )
            service_duration = context.user_data.get(
                "service_duration"
            )

            if (
                not category_name
                or not category_icon
                or not service_title
                or not service_duration
            ):
                raise ValueError(
                    "Данные услуги устарели. "
                    "Начните добавление заново."
                )

            normalized_service_title = service_title.strip()

            duplicate = db.scalar(
                select(Service.id)
                .where(
                    Service.master_id == master.id,
                    func.lower(func.trim(Service.title))
                    == normalized_service_title.lower(),
                )
                .limit(1)
            )

            if duplicate is not None:
                raise ValueError(
                    "Услуга с таким названием уже существует."
                )

            category = get_or_create_category(
                db,
                category_name,
                category_icon,
            )

            service = Service(
                master_id=master.id,
                category_id=category.id,
                title=normalized_service_title,
                duration=service_duration,
                price=price,
            )

            db.add(service)
            db.commit()
            db.refresh(service)

            service_id = service.id
            title = service.title
            duration = service.duration
            service_price = service.price
            booking_enabled = master.booking_enabled

        except ValueError as error:
            db.rollback()
            cancel_service_creation(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=(
                    master_actions_menu(
                        master.booking_enabled
                    )
                    if "master" in locals()
                    and master is not None
                    else main_menu(
                        telegram_id=update.effective_user.id,
                    )
                ),
            )
            return True

        except IntegrityError:
            db.rollback()
            cancel_service_creation(context)

            await update.message.reply_text(
                "❌ Услуга с таким названием уже существует.",
                reply_markup=(
                    master_actions_menu(
                        master.booking_enabled
                    )
                    if "master" in locals()
                    and master is not None
                    else main_menu(
                        telegram_id=update.effective_user.id,
                    )
                ),
            )
            return True

        except Exception:
            db.rollback()
            cancel_service_creation(context)

            await update.message.reply_text(
                "❌ Не удалось сохранить услугу. Попробуйте позже.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        finally:
            db.close()

        cancel_service_creation(context)

        await update.message.reply_text(
            "✅ Услуга успешно добавлена!\n\n"
            f"ID: {service_id}\n"
            f"Название: {title}\n"
            f"Длительность: {duration} мин.\n"
            f"Цена: {service_price} сом",
            reply_markup=master_actions_menu(
                booking_enabled
            ),
        )
        return True

    return False
