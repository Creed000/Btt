import re
from datetime import timedelta

from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.salon import Salon
from app.models.user import User
from app.services.timezone import local_naive_now


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
    value = re.sub(r"[^a-zа-я0-9]+", "-", value)
    value = value.strip("-")

    if not value:
        value = "salon"

    return f"{value}-{telegram_id}"[:100]


async def begin_salon_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    clear_salon_registration(context)
    context.user_data["salon_registration"] = "name"

    await update.message.reply_text(
        "🏢 Регистрация салона\n\n"
        "Шаг 1 из 3. Введите название салона.",
        reply_markup=salon_registration_menu(),
    )


async def process_salon_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("salon_registration")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить регистрацию салона":
        clear_salon_registration(context)

        await update.message.reply_text(
            "❌ Регистрация салона отменена.",
            reply_markup=main_menu(),
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
                    User.telegram_id == update.effective_user.id
                )
            )

            if user is None:
                raise ValueError(
                    "Пользователь не найден. Отправьте /start."
                )

            existing_salon = db.scalar(
                select(Salon).where(
                    Salon.owner_id == user.id,
                    Salon.is_active.is_(True),
                )
            )

            if existing_salon is not None:
                raise ValueError(
                    "У вас уже есть активный салон."
                )

            salon_name = context.user_data["salon_name"]
            salon_city = context.user_data["salon_city"]
            salon_address = text

            slug = make_slug(
                salon_name,
                user.telegram_id,
            )

            existing_slug = db.scalar(
                select(Salon).where(
                    Salon.slug == slug
                )
            )

            now = local_naive_now()

            if existing_slug is not None:
                slug = f"{slug[:90]}-{int(now.timestamp())}"

            salon = Salon(
                owner_id=user.id,
                name=salon_name,
                slug=slug,
                city=salon_city,
                address=salon_address,
                plan="free",
                subscription_status="trial",
                trial_ends_at=now + timedelta(days=14),
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

            if user.role == "client":
                user.role = "owner"

            db.add(user)
            db.commit()
            db.refresh(salon)

            salon_id = salon.id
            salon_slug = salon.slug
            trial_ends_at = salon.trial_ends_at

        except ValueError as error:
            db.rollback()
            clear_salon_registration(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(),
            )
            return True

        except Exception:
            db.rollback()
            clear_salon_registration(context)

            await update.message.reply_text(
                "❌ Не удалось создать салон. Попробуйте позже.",
                reply_markup=main_menu(),
            )
            return True

        finally:
            db.close()

        clear_salon_registration(context)

        await update.message.reply_text(
            "🎉 Салон успешно создан!\n\n"
            f"ID салона: {salon_id}\n"
            f"Slug: {salon_slug}\n"
            f"Тариф: free\n"
            f"Пробный период до: "
            f"{trial_ends_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            "Также создан главный филиал.",
            reply_markup=main_menu(role="owner"),
        )
        return True

    return False
