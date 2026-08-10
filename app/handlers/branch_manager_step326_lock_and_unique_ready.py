from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

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


def get_user_and_salon(
    db,
    telegram_id: int,
) -> tuple[User | None, Salon | None]:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if (
        user is None
        or not user.is_active
    ):
        return user, None

    salon = db.scalar(
        select(Salon)
        .where(
            Salon.owner_id == user.id,
            Salon.is_active.is_(True),
        )
        .order_by(Salon.id.asc())
        .limit(1)
    )

    return user, salon


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


async def begin_branch_creation(
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
        user, salon = get_user_and_salon(
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

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    user,
                    update.effective_user.id,
                ),
            )
            return

        require_active_salon_access(
            salon
        )

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
                    update.effective_user.id,
                ),
            )
            return

    except ValueError as error:
        await update.message.reply_text(
            f"⛔ {error}",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )
        return

    finally:
        db.close()

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

    text = " ".join(
        update.message.text.strip().split()
    )

    if text == "❌ Отменить добавление филиала":
        clear_branch_creation(
            context
        )

        db = SessionLocal()

        try:
            user, _ = get_user_and_salon(
                db,
                update.effective_user.id,
            )

            reply_markup = user_main_menu(
                db,
                user,
                update.effective_user.id,
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

        if not 2 <= len(normalized_name) <= 100:
            await update.message.reply_text(
                "Название должно содержать "
                "от 2 до 100 символов."
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

    if stage != "address":
        clear_branch_creation(
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
        user = db.scalar(
            select(User)
            .where(
                User.telegram_id
                == update.effective_user.id
            )
            .with_for_update()
        )

        if (
            user is None
            or not user.is_active
        ):
            raise ValueError(
                "Пользователь не найден или отключён."
            )

        # Блокировка строки салона сериализует
        # одновременное создание филиалов.
        salon = db.scalar(
            select(Salon)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .order_by(Salon.id.asc())
            .limit(1)
            .with_for_update()
        )

        if salon is None:
            raise ValueError(
                "Активный салон не найден."
            )

        require_active_salon_access(
            salon
        )

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
                "Данные филиала потеряны. "
                "Начните добавление заново."
            )

        normalized_branch_name = branch_name.strip()

        existing_branch = db.scalar(
            select(Branch.id).where(
                Branch.salon_id == salon.id,
                func.lower(func.trim(Branch.name))
                == normalized_branch_name.lower(),
            )
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
        db.flush()

        branch_id = branch.id
        branch_name = branch.name
        branch_address = branch.address

        db.commit()

    except ValueError as error:
        db.rollback()
        clear_branch_creation(
            context
        )

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )
        return True

    except IntegrityError:
        db.rollback()
        clear_branch_creation(
            context
        )

        await update.message.reply_text(
            "❌ Филиал с таким названием уже существует.",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
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

    db = SessionLocal()

    try:
        current_user, _ = get_user_and_salon(
            db,
            update.effective_user.id,
        )

        reply_markup = user_main_menu(
            db,
            current_user,
            update.effective_user.id,
        )
    finally:
        db.close()

    await update.message.reply_text(
        "✅ Филиал успешно создан!\n\n"
        f"ID: {branch_id}\n"
        f"Название: {branch_name}\n"
        f"Адрес: {branch_address}",
        reply_markup=reply_markup,
    )
    return True


async def delete_branch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    branch_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User)
            .where(
                User.telegram_id
                == update.effective_user.id
            )
            .with_for_update()
        )

        if (
            user is None
            or not user.is_active
        ):
            raise ValueError(
                "Пользователь не найден или отключён."
            )

        salon = db.scalar(
            select(Salon)
            .where(
                Salon.owner_id == user.id,
                Salon.is_active.is_(True),
            )
            .order_by(Salon.id.asc())
            .limit(1)
            .with_for_update()
        )

        if salon is None:
            raise ValueError(
                "Активный салон не найден."
            )

        branch = db.scalar(
            select(Branch)
            .where(
                Branch.id == branch_id,
                Branch.salon_id == salon.id,
            )
            .with_for_update()
        )

        if branch is None:
            raise ValueError(
                "Филиал не найден или принадлежит "
                "другому салону."
            )

        branch_count = (
            db.scalar(
                select(
                    func.count(Branch.id)
                ).where(
                    Branch.salon_id == salon.id
                )
            )
            or 0
        )

        if branch_count <= 1:
            raise ValueError(
                "Нельзя удалить последний филиал салона."
            )

        assigned_masters = (
            db.scalar(
                select(
                    func.count(Master.id)
                ).where(
                    Master.salon_id == salon.id,
                    Master.branch_id == branch.id,
                )
            )
            or 0
        )

        if assigned_masters > 0:
            raise ValueError(
                "Нельзя удалить филиал: "
                f"к нему привязано мастеров: {assigned_masters}. "
                "Сначала переназначьте их в другой филиал."
            )

        branch_name = branch.name

        db.delete(branch)
        db.commit()

        await update.message.reply_text(
            "✅ Филиал удалён.\n\n"
            f"Название: {branch_name}",
            reply_markup=user_main_menu(
                db,
                user,
                update.effective_user.id,
            ),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                user if "user" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось удалить филиал.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def branch_delete_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.message.text is None
    ):
        return

    prefix = "🗑 Удалить филиал #"
    text_value = update.message.text.strip()

    if not text_value.startswith(
        prefix
    ):
        return

    raw_id = text_value.removeprefix(
        prefix
    ).strip()

    if not raw_id.isdigit():
        return

    await delete_branch(
        update,
        context,
        int(raw_id),
    )


branch_delete_handler = MessageHandler(
    filters.Regex(
        r"^🗑 Удалить филиал #[0-9]+$"
    ),
    branch_delete_router,
)
