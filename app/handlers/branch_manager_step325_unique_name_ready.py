from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.subscription_access import require_active_salon_access
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


def get_user(
    db,
    telegram_id: int,
) -> User | None:
    return db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )


def get_owned_salon(
    db,
    user: User,
) -> Salon | None:
    return db.scalar(
        select(Salon).where(
            Salon.owner_id == user.id,
            Salon.is_active.is_(True),
        )
    )


def user_main_menu(
    db,
    user: User,
    *,
    has_salon: bool,
) -> ReplyKeyboardMarkup:
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


async def begin_branch_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = get_user(
            db,
            update.effective_user.id,
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
                    has_salon=False,
                ),
            )
            return

        salon = get_owned_salon(
            db,
            user,
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    has_salon=False,
                ),
            )
            return

        try:
            require_active_salon_access(
                salon
            )
        except ValueError as error:
            db.rollback()

            await update.message.reply_text(
                f"⛔ {error}",
                reply_markup=user_main_menu(
                    db,
                    user,
                    has_salon=True,
                ),
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
                "Откройте «💳 Тариф и подписка», "
                "чтобы выбрать другой тариф.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    has_salon=True,
                ),
            )
            return

        clear_branch_creation(
            context
        )
        context.user_data[
            "branch_creation"
        ] = "name"

        await update.message.reply_text(
            "🏬 Добавление филиала\n\n"
            "Шаг 1 из 2. Введите название филиала.\n\n"
            "Например: Филиал в центре",
            reply_markup=branch_creation_menu(),
        )

    finally:
        db.close()


async def process_branch_creation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get(
        "branch_creation"
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

    if text == "❌ Отменить добавление филиала":
        clear_branch_creation(
            context
        )

        db = SessionLocal()

        try:
            user = get_user(
                db,
                update.effective_user.id,
            )

            reply_markup = (
                user_main_menu(
                    db,
                    user,
                    has_salon=(
                        get_owned_salon(
                            db,
                            user,
                        )
                        is not None
                    ),
                )
                if user is not None
                else main_menu(
                    telegram_id=update.effective_user.id,
                )
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Добавление филиала отменено.",
            reply_markup=reply_markup,
        )
        return True

    if stage == "name":
        normalized_name = text.strip()

        if len(normalized_name) < 2 or len(normalized_name) > 100:
            await update.message.reply_text(
                "Название должно содержать от 2 до 100 символов."
            )
            return True

        context.user_data[
            "branch_name"
        ] = normalized_name
        context.user_data[
            "branch_creation"
        ] = "address"

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
            user = get_user(
                db,
                update.effective_user.id,
            )

            if user is None:
                raise ValueError(
                    "Пользователь не найден. Отправьте /start."
                )

            if not user.is_active:
                raise ValueError(
                    "Ваш аккаунт временно отключён."
                )

            salon = get_owned_salon(
                db,
                user,
            )

            if salon is None:
                raise ValueError(
                    "Активный салон не найден."
                )

            require_active_salon_access(
                salon
            )

            # Проверяем лимит повторно непосредственно
            # перед созданием филиала.
            allowed, reason = can_add_branch(
                db,
                salon,
            )

            if not allowed:
                raise ValueError(
                    reason
                )

            branch_name = context.user_data.get(
                "branch_name"
            )

            if not branch_name:
                raise ValueError(
                    "Данные регистрации филиала устарели. "
                    "Начните добавление заново."
                )

            normalized_branch_name = branch_name.strip()

            existing_branch = db.scalar(
                select(Branch.id)
                .where(
                    Branch.salon_id == salon.id,
                    func.lower(func.trim(Branch.name))
                    == normalized_branch_name.lower(),
                )
                .limit(1)
            )

            if existing_branch is not None:
                raise ValueError(
                    "Филиал с таким названием уже существует."
                )

            branch = Branch(
                salon_id=salon.id,
                name=normalized_branch_name,
                address=text,
            )

            db.add(branch)
            db.commit()
            db.refresh(branch)

            branch_id = branch.id
            created_name = branch.name
            branch_address = branch.address

            reply_markup = user_main_menu(
                db,
                user,
                has_salon=True,
            )

        except ValueError as error:
            db.rollback()
            clear_branch_creation(
                context
            )

            user = get_user(
                db,
                update.effective_user.id,
            )

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=(
                    user_main_menu(
                        db,
                        user,
                        has_salon=(
                            get_owned_salon(
                                db,
                                user,
                            )
                            is not None
                        ),
                    )
                    if user is not None
                    else main_menu(
                        telegram_id=update.effective_user.id,
                    )
                ),
            )
            return True

        except IntegrityError:
            db.rollback()
            clear_branch_creation(
                context
            )

            user = get_user(
                db,
                update.effective_user.id,
            )

            await update.message.reply_text(
                "❌ Филиал с таким названием уже существует.",
                reply_markup=(
                    user_main_menu(
                        db,
                        user,
                        has_salon=(
                            get_owned_salon(
                                db,
                                user,
                            )
                            is not None
                        ),
                    )
                    if user is not None
                    else main_menu(
                        telegram_id=update.effective_user.id,
                    )
                ),
            )
            return True

        except Exception:
            db.rollback()
            clear_branch_creation(
                context
            )

            await update.message.reply_text(
                "❌ Не удалось создать филиал. "
                "Попробуйте позже.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        finally:
            db.close()

        clear_branch_creation(
            context
        )

        await update.message.reply_text(
            "✅ Филиал успешно создан!\n\n"
            f"ID: {branch_id}\n"
            f"Название: {created_name}\n"
            f"Адрес: {branch_address}",
            reply_markup=reply_markup,
        )
        return True

    return False
