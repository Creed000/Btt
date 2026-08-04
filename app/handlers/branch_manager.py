from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.salon import Salon
from app.models.user import User
from app.services.subscription_limits import can_add_branch


def branch_creation_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("❌ Отменить добавление филиала")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите данные филиала",
    )


def clear_branch_creation(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "branch_creation",
        "branch_name",
    ):
        context.user_data.pop(key, None)


async def begin_branch_creation(
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
                reply_markup=main_menu(),
            )
            return

        if user.role not in {"owner", "admin"}:
            await update.message.reply_text(
                "⛔ Добавлять филиалы может только владелец салона.",
                reply_markup=main_menu(role=user.role),
            )
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(role=user.role),
            )
            return

        allowed, reason = can_add_branch(
            db,
            salon,
        )

        if not allowed:
            await update.message.reply_text(
                "⛔ Лимит тарифа достигнут.\n\n"
                f"{reason}\n\n"
                "Откройте «💳 Тариф и подписка», чтобы выбрать другой тариф.",
                reply_markup=main_menu(role=user.role),
            )
            return

    finally:
        db.close()

    clear_branch_creation(context)
    context.user_data["branch_creation"] = "name"

    await update.message.reply_text(
        "🏬 Добавление филиала\n\n"
        "Шаг 1 из 2. Введите название филиала.\n\n"
        "Например: Филиал в центре",
        reply_markup=branch_creation_menu(),
    )


async def process_branch_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("branch_creation")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить добавление филиала":
        clear_branch_creation(context)

        await update.message.reply_text(
            "❌ Добавление филиала отменено.",
            reply_markup=main_menu(role="owner"),
        )
        return True

    if stage == "name":
        if len(text) < 2 or len(text) > 100:
            await update.message.reply_text(
                "Название должно содержать от 2 до 100 символов."
            )
            return True

        context.user_data["branch_name"] = text
        context.user_data["branch_creation"] = "address"

        await update.message.reply_text(
            "Шаг 2 из 2. Введите адрес филиала.\n\n"
            "Например: ул. Манаса, 45"
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

            if user.role not in {"owner", "admin"}:
                raise ValueError(
                    "Добавлять филиалы может только владелец салона."
                )

            salon = db.scalar(
                select(Salon).where(
                    Salon.owner_id == user.id,
                    Salon.is_active.is_(True),
                )
            )

            if salon is None:
                raise ValueError(
                    "Активный салон не найден."
                )

            allowed, reason = can_add_branch(
                db,
                salon,
            )

            if not allowed:
                raise ValueError(reason)

            existing_branch = db.scalar(
                select(Branch).where(
                    Branch.salon_id == salon.id,
                    Branch.name == context.user_data["branch_name"],
                )
            )

            if existing_branch is not None:
                raise ValueError(
                    "Филиал с таким названием уже существует."
                )

            branch = Branch(
                salon_id=salon.id,
                name=context.user_data["branch_name"],
                address=text,
            )

            db.add(branch)
            db.commit()
            db.refresh(branch)

            branch_id = branch.id
            branch_name = branch.name
            branch_address = branch.address

        except ValueError as error:
            db.rollback()
            clear_branch_creation(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(role="owner"),
            )
            return True

        except Exception:
            db.rollback()
            clear_branch_creation(context)

            await update.message.reply_text(
                "❌ Не удалось создать филиал. Попробуйте позже.",
                reply_markup=main_menu(role="owner"),
            )
            return True

        finally:
            db.close()

        clear_branch_creation(context)

        await update.message.reply_text(
            "✅ Филиал успешно создан!\n\n"
            f"ID: {branch_id}\n"
            f"Название: {branch_name}\n"
            f"Адрес: {branch_address}",
            reply_markup=main_menu(role="owner"),
        )
        return True

    return False
