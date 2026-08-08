import re
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import is_platform_admin
from app.services.plan_catalog import (
    DEFAULT_PLAN_CODE,
    get_plan_title,
)
from app.services.timezone import local_naive_now


TRIAL_DAYS = 14


def salon_registration_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    "❌ Отменить регистрацию салона"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите данные салона",
    )


def clear_salon_registration(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "salon_registration",
        "salon_name",
        "salon_city",
        "salon_address",
    ):
        context.user_data.pop(key, None)


def normalize_text(
    value: str,
) -> str:
    return " ".join(
        value.strip().split()
    )


def make_slug(
    name: str,
    telegram_id: int,
) -> str:
    value = name.lower().strip()
    value = re.sub(
        r"[^a-zа-яё0-9]+",
        "-",
        value,
    )
    value = value.strip("-")

    if not value:
        value = "salon"

    suffix = str(
        telegram_id
    )

    max_name_length = (
        100 - len(suffix) - 1
    )

    return (
        f"{value[:max_name_length]}-{suffix}"
    )


def unique_slug(
    db,
    name: str,
    telegram_id: int,
) -> str:
    base_slug = make_slug(
        name,
        telegram_id,
    )

    existing = db.scalar(
        select(Salon.id).where(
            Salon.slug == base_slug
        )
    )

    if existing is None:
        return base_slug

    suffix = uuid4().hex[:8]

    return (
        f"{base_slug[:91]}-{suffix}"
    )


def user_main_menu(
    db,
    user: User | None,
    telegram_id: int,
):
    if user is None:
        return main_menu(
            telegram_id=telegram_id,
        )

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

    has_master = (
        db.scalar(
            select(Master.id)
            .where(
                Master.user_id == user.id
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=user.role,
        telegram_id=telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


async def begin_salon_registration(
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
        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. "
                "Отправьте /start.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        if not user.is_active:
            await update.message.reply_text(
                "⛔ Ваш аккаунт временно отключён.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        existing_salon = db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )

        if existing_salon is not None:
            await update.message.reply_text(
                "ℹ️ У вас уже есть активный салон.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        clear_salon_registration(
            context
        )
        context.user_data[
            "salon_registration"
        ] = "name"

        await update.message.reply_text(
            "🏢 Регистрация салона\n\n"
            "Шаг 1 из 3. Введите название салона.",
            reply_markup=salon_registration_menu(),
        )

    finally:
        db.close()


async def process_salon_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get(
        "salon_registration"
    )

    if stage is None:
        return False

    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text = normalize_text(
        update.message.text
    )

    if text == "❌ Отменить регистрацию салона":
        clear_salon_registration(
            context
        )

        db = SessionLocal()

        try:
            user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )

            reply_markup = user_main_menu(
                db,
                user,
                update.effective_user.id,
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Регистрация салона отменена.",
            reply_markup=reply_markup,
        )
        return True

    if stage == "name":
        if not 2 <= len(text) <= 150:
            await update.message.reply_text(
                "Название должно содержать "
                "от 2 до 150 символов."
            )
            return True

        context.user_data[
            "salon_name"
        ] = text
        context.user_data[
            "salon_registration"
        ] = "city"

        await update.message.reply_text(
            "Шаг 2 из 3. Введите город салона.\n\n"
            "Например: Бишкек"
        )
        return True

    if stage == "city":
        if not 2 <= len(text) <= 100:
            await update.message.reply_text(
                "Название города должно содержать "
                "от 2 до 100 символов."
            )
            return True

        context.user_data[
            "salon_city"
        ] = text
        context.user_data[
            "salon_registration"
        ] = "address"

        await update.message.reply_text(
            "Шаг 3 из 3. Введите адрес салона.\n\n"
            "Например: ул. Киевская, 120"
        )
        return True

    if stage != "address":
        clear_salon_registration(
            context
        )
        return False

    if not 3 <= len(text) <= 255:
        await update.message.reply_text(
            "Адрес должен содержать "
            "от 3 до 255 символов."
        )
        return True

    db = SessionLocal()

    try:
        # Блокируем строку пользователя на PostgreSQL,
        # чтобы два одновременных подтверждения
        # не создали два активных салона.
        user = db.scalar(
            select(User)
            .where(
                User.telegram_id
                == update.effective_user.id
            )
            .with_for_update()
        )

        if user is None:
            raise ValueError(
                "Пользователь не найден. "
                "Отправьте /start."
            )

        if not user.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        existing_salon = db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )

        if existing_salon is not None:
            raise ValueError(
                "У вас уже есть активный салон."
            )

        salon_name = context.user_data.get(
            "salon_name"
        )
        salon_city = context.user_data.get(
            "salon_city"
        )

        if not salon_name or not salon_city:
            raise ValueError(
                "Данные регистрации потеряны. "
                "Начните регистрацию заново."
            )

        salon_address = text
        now = local_naive_now()

        salon = Salon(
            owner_id=user.id,
            name=salon_name,
            slug=unique_slug(
                db,
                salon_name,
                user.telegram_id,
            ),
            city=salon_city,
            address=salon_address,
            plan=DEFAULT_PLAN_CODE,
            subscription_status="trial",
            trial_ends_at=(
                now
                + timedelta(
                    days=TRIAL_DAYS
                )
            ),
            subscription_ends_at=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        db.add(salon)
        db.flush()

        branch = Branch(
            salon_id=salon.id,
            name="Главный филиал",
            address=salon_address,
        )

        db.add(branch)

        # Системный админ определяется по Telegram ID,
        # поэтому его бизнес-роль менять не требуется.
        # Обычный клиент/мастер становится владельцем.
        if (
            not is_platform_admin(
                user.telegram_id
            )
            and user.role in {
                "client",
                "master",
            }
        ):
            user.role = "owner"

        db.add(user)
        db.commit()

        salon_id = salon.id
        salon_slug = salon.slug
        trial_ends_at = salon.trial_ends_at
        plan_title = get_plan_title(
            salon.plan
        )

        has_master = (
            db.scalar(
                select(Master.id)
                .where(
                    Master.user_id
                    == user.id
                )
                .limit(1)
            )
            is not None
        )

        role = user.role

    except ValueError as error:
        db.rollback()
        clear_salon_registration(
            context
        )

        try:
            user_for_menu = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
        except Exception:
            db.rollback()
            user_for_menu = None

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                user_for_menu,
                update.effective_user.id,
            ),
        )
        return True

    except Exception:
        db.rollback()
        clear_salon_registration(
            context
        )

        await update.message.reply_text(
            "❌ Не удалось создать салон. "
            "Попробуйте позже.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return True

    finally:
        db.close()

    clear_salon_registration(
        context
    )

    await update.message.reply_text(
        "🎉 Салон успешно создан!\n\n"
        f"ID салона: {salon_id}\n"
        f"Slug: {salon_slug}\n"
        f"Тариф: {plan_title}\n"
        f"🎁 Пробный период: {TRIAL_DAYS} дней\n"
        "Действует до: "
        f"{trial_ends_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        "🏬 Главный филиал создан автоматически.",
        reply_markup=main_menu(
            role=role,
            telegram_id=update.effective_user.id,
            has_salon=True,
            has_master=has_master,
        ),
    )

    return True
