from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.bookings import create_booking
from app.database.session import SessionLocal
from app.handlers.admin_controls import (
    change_master_verified_status,
    change_user_active_status,
)
from app.handlers.admin_management import (
    show_admin_bookings,
    show_admin_masters,
    show_admin_statistics,
    show_admin_users,
)
from app.handlers.admin_panel import open_admin_panel
from app.handlers.admin_subscriptions import (
    activate_salon_plan,
    disable_salon_subscription,
    open_salon_subscription_control,
    show_salons_for_subscription,
)
from app.handlers.booking import booking
from app.handlers.branch_manager import (
    begin_branch_creation,
    process_branch_creation,
)
from app.handlers.master_branch_assignment import (
    begin_branch_assignment,
    process_branch_assignment,
)
from app.handlers.master_bookings import (
    change_master_booking_status,
    show_master_bookings,
)
from app.handlers.master_city import (
    begin_master_city_selection,
    process_master_city_selection,
)
from app.handlers.master_day_off_manager import (
    begin_day_off_creation,
    delete_master_day_off,
    open_day_off_panel,
    process_day_off_creation,
    show_master_days_off,
)
from app.handlers.master_invite import (
    begin_master_invite,
    process_master_invite,
)
from app.handlers.master_panel import become_master
from app.handlers.master_schedule_manager import (
    begin_schedule_setup,
    process_schedule_setup,
    show_master_schedule,
)
from app.handlers.master_time_block_manager import (
    begin_time_block_creation,
    delete_master_time_block,
    open_time_blocks_panel,
    process_time_block_creation,
    show_master_time_blocks,
)
from app.handlers.profile import profile
from app.handlers.salon_dashboard import (
    open_salon_dashboard,
    show_salon_branches,
    show_salon_masters,
)
from app.handlers.salon_registration import (
    begin_salon_registration,
    process_salon_registration,
)
from app.handlers.search import search
from app.handlers.settings_panel import (
    open_settings_panel,
)
from app.handlers.settings_language import (
    change_user_language,
    open_language_settings,
)
from app.handlers.service_manager import (
    begin_add_service,
    delete_master_service,
    process_service_creation,
    show_master_services,
    toggle_master_booking,
)
from app.handlers.subscription_plans import (
    request_plan_change,
    show_available_plans,
)
from app.keyboards.available_time import available_time_menu
from app.keyboards.category import category_menu
from app.keyboards.confirm import confirm_menu
from app.keyboards.date import date_menu
from app.keyboards.main import main_menu
from app.keyboards.master import master_menu
from app.keyboards.service import service_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.service import Service
from app.models.user import User
from app.services.availability import get_available_slots
from app.services.booking_catalog import (
    get_available_master_services,
    resolve_selected_service,
)
from app.services.booking_selection import (
    EMPTY_CATEGORY_BUTTON,
    EMPTY_CITY_BUTTON,
    resolve_category_button,
    resolve_city_button,
)
from app.services.booking_slot_validation import (
    validate_selected_booking_slot,
)
from app.services.booking_notifications import (
    notify_master_about_client_cancellation,
    notify_master_about_new_booking,
)
from app.services.navigation import show_main_menu
from app.services.timezone import local_naive_now, local_today


def clear_booking_data(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "city",
        "category",
        "master_id",
        "master_name",
        "service_id",
        "service_title",
        "booking_date",
        "booking_time",
    ):
        context.user_data.pop(key, None)


async def cancel_client_booking(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    booking_id: int,
) -> None:
    if update.message is None or update.effective_user is None:
        return

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
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        booking_item = db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.client),
                joinedload(Booking.service),
                joinedload(Booking.master).joinedload(Master.user),
            )
            .where(
                Booking.id == booking_id,
                Booking.client_id == user.id,
            )
        )

        if booking_item is None:
            await update.message.reply_text(
                "❌ Запись не найдена или принадлежит другому пользователю.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        if booking_item.status == "cancelled":
            await update.message.reply_text(
                "ℹ️ Эта запись уже отменена.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        if booking_item.status == "completed":
            await update.message.reply_text(
                "❌ Завершённую запись отменить нельзя.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        if booking_item.status not in {"new", "confirmed"}:
            await update.message.reply_text(
                "❌ Эту запись нельзя отменить в текущем статусе.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        starts_at = datetime.combine(
            booking_item.booking_date,
            booking_item.booking_time,
        )

        if starts_at <= local_naive_now():
            await update.message.reply_text(
                "❌ Прошедшую запись отменить нельзя.",
                reply_markup=main_menu(
                    role=user.role,
                    telegram_id=user.telegram_id,
                ),
            )
            return

        booking_item.status = "cancelled"
        db.commit()
        db.expunge_all()

        notification_delivered = (
            await notify_master_about_client_cancellation(
                context.application,
                booking_item,
            )
        )

        notification_text = (
            "Мастер получил уведомление."
            if notification_delivered
            else (
                "Запись отменена, но уведомление мастеру "
                "доставить не удалось."
            )
        )

        await update.message.reply_text(
            f"✅ Запись #{booking_id} отменена.\n"
            f"{notification_text}",
            reply_markup=main_menu(
                role=user.role,
                telegram_id=user.telegram_id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отменить запись. Попробуйте позже.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return

    text = update.message.text.strip()

    language_handled = await change_user_language(
        update,
        context,
    )

    if language_handled:
        return

    if context.user_data.get("time_block_setup"):
        handled = await process_time_block_creation(update, context)
        if handled:
            return

    if context.user_data.get("day_off_setup"):
        handled = await process_day_off_creation(update, context)
        if handled:
            return

    if context.user_data.get("schedule_setup"):
        handled = await process_schedule_setup(update, context)
        if handled:
            return

    if context.user_data.get("branch_assignment"):
        handled = await process_branch_assignment(update, context)
        if handled:
            return

    if context.user_data.get("master_invite"):
        handled = await process_master_invite(update, context)
        if handled:
            return

    if context.user_data.get("branch_creation"):
        handled = await process_branch_creation(update, context)
        if handled:
            return

    if context.user_data.get("salon_registration"):
        handled = await process_salon_registration(update, context)
        if handled:
            return

    if context.user_data.get("master_city_selection"):
        handled = await process_master_city_selection(update, context)
        if handled:
            return

    if context.user_data.get("service_creation"):
        handled = await process_service_creation(update, context)
        if handled:
            return

    # Салон.
    if text == "🏢 Создать салон":
        await begin_salon_registration(update, context)
        return

    if text in {"🏢 Кабинет салона", "🏢 Мой салон"}:
        await open_salon_dashboard(update, context)
        return

    if text == "🏬 Мои филиалы":
        await show_salon_branches(update, context)
        return

    if text == "👥 Мастера салона":
        await show_salon_masters(update, context)
        return

    if text == "➕ Добавить филиал":
        await begin_branch_creation(update, context)
        return

    if text == "➕ Добавить мастера":
        await begin_master_invite(update, context)
        return

    if text == "🏬 Назначить филиал мастеру":
        await begin_branch_assignment(update, context)
        return

    if text == "💳 Тариф и подписка":
        await show_available_plans(update, context)
        return

    if text.startswith("💳 Выбрать тариф "):
        plan_title = text.replace(
            "💳 Выбрать тариф ",
            "",
            1,
        ).strip()

        await request_plan_change(
            update,
            context,
            plan_title=plan_title,
        )
        return

    if text.startswith("✅ Текущий тариф:"):
        await show_available_plans(update, context)
        return

    # Админ-панель.
    if text == "👑 Админ-панель":
        await open_admin_panel(update, context)
        return

    if text.startswith("⛔ Заблокировать пользователя #"):
        try:
            user_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить пользователя.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_user_active_status(
            update,
            context,
            user_id=user_id,
            is_active=False,
        )
        return

    if text.startswith("✅ Разблокировать пользователя #"):
        try:
            user_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить пользователя.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_user_active_status(
            update,
            context,
            user_id=user_id,
            is_active=True,
        )
        return

    if text.startswith("✅ Подтвердить мастера #"):
        try:
            master_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить мастера.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_master_verified_status(
            update,
            context,
            master_id=master_id,
            is_verified=True,
        )
        return

    if text.startswith("↩️ Снять проверку мастера #"):
        try:
            master_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить мастера.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_master_verified_status(
            update,
            context,
            master_id=master_id,
            is_verified=False,
        )
        return

    if text == "👥 Пользователи":
        await show_admin_users(update, context)
        return

    if text == "🧑‍💼 Мастера":
        await show_admin_masters(update, context)
        return

    if text == "📅 Все записи":
        await show_admin_bookings(update, context)
        return

    if text == "📊 Статистика":
        await show_admin_statistics(update, context)
        return

    if text == "💳 Подписки салонов":
        await show_salons_for_subscription(update, context)
        return

    if text.startswith("💳 Управлять салоном #"):
        try:
            salon_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить салон.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await open_salon_subscription_control(
            update,
            salon_id=salon_id,
        )
        return

    if text.startswith("✅ Активировать "):
        try:
            action_text, salon_id_text = text.rsplit(
                " для салона #",
                1,
            )
            salon_id = int(salon_id_text)
            plan_title = action_text.replace(
                "✅ Активировать ",
                "",
                1,
            ).strip()
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить тариф или салон.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        plan_codes = {
            "Free": "free",
            "Basic": "basic",
            "Pro": "pro",
            "Business": "business",
        }
        plan_code = plan_codes.get(plan_title)

        if plan_code is None:
            await update.message.reply_text(
                "❌ Неизвестный тариф.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await activate_salon_plan(
            update,
            salon_id=salon_id,
            plan_code=plan_code,
        )
        return

    if text.startswith("⛔ Отключить подписку салона #"):
        try:
            salon_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить салон.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await disable_salon_subscription(
            update,
            salon_id=salon_id,
        )
        return

    # Кабинет мастера.
    if text == "🏙 Мой город":
        await begin_master_city_selection(update, context)
        return

    if text == "🗓 Моё расписание":
        await show_master_schedule(update, context)
        return

    if text == "⚙️ Настроить расписание":
        await begin_schedule_setup(update, context)
        return

    if text == "🏖 Выходные даты":
        await open_day_off_panel(update, context)
        return

    if text == "➕ Добавить выходной":
        await begin_day_off_creation(update, context)
        return

    if text == "📋 Мои выходные даты":
        await show_master_days_off(update, context)
        return

    if text.startswith("🗑 Удалить выходной #"):
        try:
            day_off_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить выходной.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await delete_master_day_off(
            update,
            day_off_id=day_off_id,
        )
        return

    if text == "⏸ Блокировки времени":
        await open_time_blocks_panel(update, context)
        return

    if text == "➕ Добавить блокировку времени":
        await begin_time_block_creation(update, context)
        return

    if text == "📋 Мои блокировки времени":
        await show_master_time_blocks(update, context)
        return

    if text.startswith("🗑 Удалить блокировку #"):
        try:
            block_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить блокировку.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await delete_master_time_block(
            update,
            block_id=block_id,
        )
        return

    if text == "➕ Добавить услугу":
        await begin_add_service(update, context)
        return

    if text == "📋 Мои услуги":
        await show_master_services(update, context)
        return

    if text.startswith("🗑 Удалить услугу #"):
        try:
            service_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер услуги.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await delete_master_service(
            update,
            context,
            service_id,
        )
        return

    if text == "⛔ Выключить запись":
        await toggle_master_booking(update, context, enabled=False)
        return

    if text == "✅ Включить запись":
        await toggle_master_booking(update, context, enabled=True)
        return

    if text == "📅 Мои записи":
        await show_master_bookings(update, context)
        return

    if text.startswith("✅ Подтвердить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_master_booking_status(
            update,
            context,
            booking_id,
            new_status="confirmed",
        )
        return

    if text.startswith("🏁 Завершить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_master_booking_status(
            update,
            context,
            booking_id,
            new_status="completed",
        )
        return

    if text.startswith("❌ Отменить заявку #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await change_master_booking_status(
            update,
            context,
            booking_id,
            new_status="cancelled",
        )
        return

    if text.startswith("❌ Отменить запись #"):
        try:
            booking_id = int(text.rsplit("#", 1)[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить номер записи.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        await cancel_client_booking(update, context, booking_id)
        return

    # Главное меню.
    if text == "📅 Записаться":
        clear_booking_data(context)
        await booking(update, context)
        return

    if text == "👤 Личный кабинет":
        await profile(update, context)
        return

    if text == "🔍 Найти мастера":
        await search(update, context)
        return

    if text == "💼 Стать мастером":
        await become_master(update, context)
        return

    if text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ Добро пожаловать в BTT!\n\n"
            "📅 Записаться — запись к мастеру\n"
            "🔍 Найти мастера — поиск по каталогу\n"
            "👤 Личный кабинет — ваши записи\n"
            "💼 Стать мастером — кабинет мастера\n"
            "⚙️ Настройки — настройки аккаунта",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    if text == "⚙️ Настройки":
        await open_settings_panel(
            update,
            context,
        )
        return

    if text == "🌐 Язык":
        await open_language_settings(
            update,
            context,
        )
        return

    # Запись клиента: динамический выбор города.
    if text == EMPTY_CITY_BUTTON:
        await update.message.reply_text(
            "🔎 Сейчас нет городов с доступными мастерами.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    if text.startswith("🏙 "):
        db = SessionLocal()

        try:
            selected_city = resolve_city_button(
                db,
                text,
            )
        finally:
            db.close()

        if selected_city is None:
            await update.message.reply_text(
                "❌ Этот город больше недоступен. "
                "Выберите город заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        context.user_data["city"] = selected_city
        context.user_data.pop("category", None)
        context.user_data.pop("master_id", None)
        context.user_data.pop("master_name", None)
        context.user_data.pop("service_id", None)
        context.user_data.pop("service_title", None)

        await update.message.reply_text(
            f"✅ Город: {selected_city}\n\n"
            "📂 Теперь выберите категорию.",
            reply_markup=category_menu(
                city_name=selected_city,
            ),
        )
        return

    # Запись клиента: динамический выбор категории.
    if text == EMPTY_CATEGORY_BUTTON:
        await update.message.reply_text(
            "🔎 В выбранном городе пока нет доступных категорий.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    selected_city = context.user_data.get("city")

    if selected_city is not None:
        db = SessionLocal()

        try:
            selected_category = resolve_category_button(
                db,
                button_text=text,
                city_name=selected_city,
            )
        finally:
            db.close()

        if selected_category is not None:
            context.user_data["category"] = selected_category
            context.user_data.pop("master_id", None)
            context.user_data.pop("master_name", None)
            context.user_data.pop("service_id", None)
            context.user_data.pop("service_title", None)

            await update.message.reply_text(
                "👤 Выберите мастера.",
                reply_markup=master_menu(
                    city_name=selected_city,
                    category_name=selected_category,
                ),
            )
            return

    if text.startswith("👤") and "#" in text:
        try:
            master_id = int(
                text.split("#", 1)[1].split()[0]
            )
            master_name = (
                text.split("·", 1)[0]
                .replace("👤", "")
                .strip()
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить мастера. "
                "Выберите его кнопкой."
            )
            return

        selected_city = context.user_data.get("city")
        selected_category = context.user_data.get("category")

        if selected_city is None or selected_category is None:
            clear_booking_data(context)

            await update.message.reply_text(
                "⚠️ Сначала выберите город и категорию.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        db = SessionLocal()

        try:
            master, services = get_available_master_services(
                db=db,
                master_id=master_id,
                city_name=selected_city,
                category_name=selected_category,
            )

            master_name = (
                master.user.first_name
                if master.user and master.user.first_name
                else master_name
            )

        except ValueError as error:
            clear_booking_data(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "❌ Не удалось загрузить услуги мастера.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        finally:
            db.close()

        context.user_data["master_id"] = master_id
        context.user_data["master_name"] = master_name
        context.user_data.pop("service_id", None)
        context.user_data.pop("service_title", None)

        await update.message.reply_text(
            f"✅ Мастер: {master_name}\n\n"
            "💼 Теперь выберите услугу:",
            reply_markup=service_menu(services),
        )
        return

    if text.startswith("💼") and "#" in text:
        try:
            service_id = int(
                text.split("#", 1)[1].split()[0]
            )
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить услугу. "
                "Выберите её кнопкой."
            )
            return

        master_id = context.user_data.get("master_id")
        selected_city = context.user_data.get("city")
        selected_category = context.user_data.get("category")

        if (
            master_id is None
            or selected_city is None
            or selected_category is None
        ):
            clear_booking_data(context)

            await update.message.reply_text(
                "⚠️ Данные выбора потеряны. "
                "Начните запись заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        db = SessionLocal()

        try:
            service = resolve_selected_service(
                db=db,
                service_id=service_id,
                master_id=master_id,
                city_name=selected_city,
                category_name=selected_category,
            )

        except ValueError as error:
            clear_booking_data(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "❌ Не удалось проверить услугу. "
                "Начните запись заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        finally:
            db.close()

        context.user_data["service_id"] = service.id
        context.user_data["service_title"] = service.title

        await update.message.reply_text(
            f"✅ Услуга: {service.title}\n"
            f"⏱ Длительность: {service.duration} мин.\n"
            f"💰 Цена: {service.price} сом\n\n"
            "📅 Выберите дату.",
            reply_markup=date_menu(),
        )
        return

    if text == "Услуг пока нет":
        clear_booking_data(context)
        await update.message.reply_text(
            "У выбранного мастера пока нет доступных услуг.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    if text.startswith("📅 ") and "·" in text:
        try:
            iso_date = text.rsplit("·", 1)[1].strip()
            selected_date = datetime.strptime(
                iso_date,
                "%Y-%m-%d",
            ).date()
        except (ValueError, IndexError):
            await update.message.reply_text(
                "❌ Не удалось определить дату. Выберите её кнопкой.",
                reply_markup=date_menu(),
            )
            return

        if selected_date < local_today():
            await update.message.reply_text(
                "❌ Нельзя выбрать прошедшую дату.",
                reply_markup=date_menu(),
            )
            return

        master_id = context.user_data.get("master_id")
        service_id = context.user_data.get("service_id")

        if master_id is None or service_id is None:
            clear_booking_data(context)
            await update.message.reply_text(
                "⚠️ Сначала выберите мастера и услугу.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        db = SessionLocal()
        try:
            slots = get_available_slots(
                db=db,
                master_id=master_id,
                service_id=service_id,
                booking_date=selected_date,
            )
        except ValueError as error:
            clear_booking_data(context)
            await update.message.reply_text(
                f"⚠️ {error}",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return
        except Exception:
            clear_booking_data(context)
            await update.message.reply_text(
                "❌ Не удалось загрузить свободное время.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return
        finally:
            db.close()

        context.user_data["booking_date"] = selected_date

        await update.message.reply_text(
            f"✅ Дата: {selected_date.strftime('%d.%m.%Y')}\n\n"
            "🕒 Выберите свободное время.",
            reply_markup=available_time_menu(slots),
        )
        return

    if text == "Свободного времени нет":
        await update.message.reply_text(
            "На выбранную дату свободных слотов нет. "
            "Выберите другую дату.",
            reply_markup=date_menu(),
        )
        return

    if text.startswith("🕒 "):
        try:
            selected_time = datetime.strptime(
                text.removeprefix("🕒 ").strip(),
                "%H:%M",
            ).time()
        except ValueError:
            await update.message.reply_text(
                "❌ Не удалось определить время. "
                "Выберите свободный слот кнопкой."
            )
            return

        master_id = context.user_data.get("master_id")
        service_id = context.user_data.get("service_id")
        selected_date = context.user_data.get("booking_date")

        if (
            master_id is None
            or service_id is None
            or selected_date is None
        ):
            clear_booking_data(context)

            await update.message.reply_text(
                "⚠️ Данные записи потеряны. "
                "Начните запись заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        db = SessionLocal()

        try:
            validate_selected_booking_slot(
                db=db,
                master_id=master_id,
                service_id=service_id,
                booking_date=selected_date,
                booking_time=selected_time,
            )

        except ValueError as error:
            try:
                slots = get_available_slots(
                    db=db,
                    master_id=master_id,
                    service_id=service_id,
                    booking_date=selected_date,
                )
            except Exception:
                slots = []

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=available_time_menu(slots),
            )
            return

        except Exception:
            clear_booking_data(context)

            await update.message.reply_text(
                "❌ Не удалось проверить свободное время. "
                "Начните запись заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        finally:
            db.close()

        context.user_data["booking_time"] = selected_time

        await update.message.reply_text(
            "📋 Подтверждение записи\n\n"
            f"🏙 Город: {context.user_data.get('city', '—')}\n"
            f"📂 Категория: {context.user_data.get('category', '—')}\n"
            f"👤 Мастер: {context.user_data.get('master_name', '—')}\n"
            f"💼 Услуга: {context.user_data.get('service_title', '—')}\n"
            f"📅 Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"🕒 Время: {selected_time.strftime('%H:%M')}\n\n"
            "Подтвердить запись?",
            reply_markup=confirm_menu(),
        )
        return

    if text == "✅ Подтвердить":
        required_fields = (
            "master_id",
            "service_id",
            "booking_date",
            "booking_time",
        )

        if not all(
            context.user_data.get(field)
            for field in required_fields
        ):
            clear_booking_data(context)
            await update.message.reply_text(
                "⚠️ Данные записи заполнены не полностью. Начните заново.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        try:
            created_booking = create_booking(
                telegram_id=update.effective_user.id,
                master_id=context.user_data["master_id"],
                service_id=context.user_data["service_id"],
                booking_date=context.user_data["booking_date"],
                booking_time=context.user_data["booking_time"],
            )
        except ValueError as error:
            clear_booking_data(context)
            await update.message.reply_text(
                f"⚠️ {error}",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return
        except Exception:
            clear_booking_data(context)
            await update.message.reply_text(
                "❌ Не удалось создать запись. Попробуйте ещё раз.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        notification_delivered = (
            await notify_master_about_new_booking(
                context.application,
                created_booking,
            )
        )

        notification_text = (
            "Мастер получил уведомление."
            if notification_delivered
            else (
                "Запись сохранена, но уведомление мастеру "
                "доставить не удалось."
            )
        )

        clear_booking_data(context)

        await update.message.reply_text(
            "🎉 Запись успешно создана!\n\n"
            f"Номер записи: {created_booking.id}\n"
            f"{notification_text}",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    if text == "❌ Отменить":
        clear_booking_data(context)
        await update.message.reply_text(
            "❌ Создание записи отменено.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    if text == "⬅️ Назад":
        clear_booking_data(context)
        await show_main_menu(
            update,
            context,
            text="🏠 Главное меню",
        )
        return

    if text in {
        "Мастеров пока нет",
        "Подходящих мастеров нет",
    }:
        await update.message.reply_text(
            "По выбранному городу и категории подходящих мастеров пока нет.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return

    await show_main_menu(
        update,
        context,
        text="Пожалуйста, используйте кнопки меню.",
    )


menu_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu,
)
