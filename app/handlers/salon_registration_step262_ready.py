import re
from datetime import timedelta

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
            [KeyboardButton("❌ Отменить регистрацию салона")],
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

    return f"{value}-{telegram_id}"[:100]


def user_main_menu(
    db,
    user: User,
) -> ReplyKeyboardMarkup:
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
        telegram_id=user.telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


async def begin_salon_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
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

        if not user.is_active:
            await update.message.reply_text(
                "❌ Ваш аккаунт временно отключён.",
                reply_markup=user_main_menu(
                    db,
                    user,
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
                ),
            )
            return

        clear_salon_registration(context)
        context.user_data["salon_registration"] = "name"

        await update.message.reply_text(
            "🏢 Регистрация салона GlowFlow\n\n"
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

    text = update.message.text.strip()

    if text == "❌ Отменить регистрацию салона":
        clear_salon_registration(context)

        db = SessionLocal()

        try:
            user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )

            reply_markup = (
                user_main_menu(db, user)
                if user is not None
                else main_menu(
                    telegram_id=update.effective_user.id
                )
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Регистрация салона отменена.",
            reply_markup=reply_markup,
        )
        return True

    if stage == "name":
        if len(text) < 2 or len(text) > 150:
            await update.message.reply_text(
                "Название должно содержать от 2 до 150 символов."
            )
            return True

        context.user_data["salon_name"] = text
        context.user_data["salon_registration"] = "city"

        await update.message.reply_text(
            "Шаг 2 из 3. Введите город салона.\n\n"
            "Например: Бишкек"
        )
        return True

    if stage == "city":
        if len(text) < 2 or len(text) > 100:
            await update.message.reply_text(
                "Название города должно содержать от 2 до 100 символов."
            )
            return True

        context.user_data["salon_city"] = text
        context.user_data["salon_registration"] = "address"

        await update.message.reply_text(
            "Шаг 3 из 3. Введите адрес салона.\n\n"
            "Например: ул. Киевская, 120"
        )
        return True

    if stage == "address":
        if len(text) < 3 or len(text) > 255:
            await update.message.reply_text(
                "Адрес должен содержать от 3 до 255 символов."
            )
            return True

        db = SessionLocal()

        try:
            user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )

            if user is None:
                raise ValueError(
                    "Пользователь не найден. Отправьте /start."
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

            salon_name = context.user_data[
                "salon_name"
            ]
            salon_city = context.user_data[
                "salon_city"
            ]
            salon_address = text

            slug = make_slug(
                salon_name,
                user.telegram_id,
            )

            existing_slug = db.scalar(
                select(Salon.id)
                .where(
                    Salon.slug == slug
                )
                .limit(1)
            )

            now = local_naive_now()

            if existing_slug is not None:
                suffix = str(
                    int(now.timestamp())
                )
                base = slug[: 99 - len(suffix)]
                slug = f"{base}-{suffix}"[:100]

            trial_ends_at = (
                now + timedelta(days=TRIAL_DAYS)
            )

            salon = Salon(
                owner_id=user.id,
                name=salon_name,
                slug=slug,
                city=salon_city,
                address=salon_address,
                plan=DEFAULT_PLAN_CODE,
                subscription_status="trial",
                trial_ends_at=trial_ends_at,
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

            # Platform-admin сохраняет роль admin.
            # Обычный client/master становится owner.
            if not is_platform_admin(
                user.telegram_id
            ):
                user.role = "owner"

            db.add(user)
            db.commit()
            db.refresh(salon)

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

            reply_markup = main_menu(
                role=user.role,
                telegram_id=user.telegram_id,
                has_salon=True,
                has_master=has_master,
            )

            salon_id = salon.id
            salon_slug = salon.slug
            plan_title = get_plan_title(
                salon.plan
            )
            trial_end = salon.trial_ends_at

        except ValueError as error:
            db.rollback()
            clear_salon_registration(context)

            user = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=(
                    user_main_menu(db, user)
                    if user is not None
                    else main_menu(
                        telegram_id=update.effective_user.id
                    )
                ),
            )
            return True

        except Exception:
            db.rollback()
            clear_salon_registration(context)

            await update.message.reply_text(
                "❌ Не удалось создать салон. Попробуйте позже.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        finally:
            db.close()

        clear_salon_registration(context)

        await update.message.reply_text(
            "🎉 Салон успешно создан!\n\n"
            f"ID салона: {salon_id}\n"
            f"Slug: {salon_slug}\n"
            f"Тариф: {plan_title}\n"
            f"Пробный период: {TRIAL_DAYS} дней\n"
            f"До: {trial_end.strftime('%d.%m.%Y %H:%M')}\n\n"
            "🏬 Главный филиал создан автоматически.",
            reply_markup=reply_markup,
        )
        return True

    return False
