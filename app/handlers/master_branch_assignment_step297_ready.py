from sqlalchemy import select
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User


def clear_branch_assignment(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "branch_assignment",
        "branch_assignment_master_id",
    ):
        context.user_data.pop(key, None)


def masters_for_branch_menu(
    masters: list[Master],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for master in masters:
        name = (
            master.user.first_name
            if master.user and master.user.first_name
            else "Без имени"
        )

        current_branch = (
            master.branch.name
            if master.branch
            else "без филиала"
        )

        keyboard.append(
            [
                KeyboardButton(
                    f"👤 Назначить {name} · #{master.id}"
                )
            ]
        )

    if not keyboard:
        keyboard.append(
            [KeyboardButton("Мастеров салона нет")]
        )

    keyboard.append(
        [KeyboardButton("❌ Отменить назначение филиала")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите мастера",
    )


def branches_for_master_menu(
    branches: list[Branch],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for branch in branches:
        keyboard.append(
            [
                KeyboardButton(
                    f"🏬 {branch.name} · #{branch.id}"
                )
            ]
        )

    if not keyboard:
        keyboard.append(
            [KeyboardButton("Филиалов салона нет")]
        )

    keyboard.append(
        [KeyboardButton("❌ Отменить назначение филиала")]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите филиал",
    )


def get_owner_and_salon(
    db,
    telegram_id: int,
) -> tuple[User | None, Salon | None]:
    owner = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if (
        owner is None
        or not owner.is_active
    ):
        return owner, None

    salon = db.scalar(
        select(Salon)
        .where(
            Salon.owner_id == owner.id,
            Salon.is_active.is_(True),
        )
        .order_by(Salon.id.asc())
        .limit(1)
    )

    return owner, salon


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


async def begin_branch_assignment(
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
        owner, salon = get_owner_and_salon(
            db,
            update.effective_user.id,
        )

        if owner is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        if not owner.is_active:
            await update.message.reply_text(
                "⛔ Ваш аккаунт временно отключён.",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            return

        masters = list(
            db.scalars(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.branch),
                )
                .where(
                    Master.salon_id == salon.id
                )
                .order_by(Master.id)
            ).unique().all()
        )

        # Отключённые аккаунты нельзя назначать,
        # пока администратор их не активирует.
        assignable_masters = [
            master
            for master in masters
            if (
                master.user is not None
                and master.user.is_active
            )
        ]

        clear_branch_assignment(
            context
        )

        if not assignable_masters:
            await update.message.reply_text(
                "ℹ️ В салоне нет активных мастеров "
                "для назначения филиала.",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            return

        context.user_data[
            "branch_assignment"
        ] = "master"

        await update.message.reply_text(
            "🏬 Назначение филиала мастеру\n\n"
            "Шаг 1 из 2. Выберите мастера:",
            reply_markup=masters_for_branch_menu(
                assignable_masters
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров салона.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def process_branch_assignment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get(
        "branch_assignment"
    )

    if stage is None:
        return False

    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text_value = update.message.text.strip()

    if text_value == "❌ Отменить назначение филиала":
        clear_branch_assignment(
            context
        )

        db = SessionLocal()

        try:
            owner, _ = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            reply_markup = user_main_menu(
                db,
                owner,
                update.effective_user.id,
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Назначение филиала отменено.",
            reply_markup=reply_markup,
        )
        return True

    if text_value in {
        "Мастеров салона нет",
        "Филиалов салона нет",
    }:
        clear_branch_assignment(
            context
        )

        db = SessionLocal()

        try:
            owner, _ = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            reply_markup = user_main_menu(
                db,
                owner,
                update.effective_user.id,
            )
        finally:
            db.close()

        await update.message.reply_text(
            "Для назначения нужны активный мастер "
            "и хотя бы один филиал.",
            reply_markup=reply_markup,
        )
        return True

    if stage == "master":
        if (
            not text_value.startswith("👤 Назначить ")
            or "#" not in text_value
        ):
            await update.message.reply_text(
                "Выберите мастера с помощью кнопки."
            )
            return True

        try:
            master_id = int(
                text_value.rsplit("#", 1)[1]
            )
        except ValueError:
            await update.message.reply_text(
                "Не удалось определить мастера."
            )
            return True

        db = SessionLocal()

        try:
            owner, salon = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            if (
                owner is None
                or salon is None
            ):
                raise ValueError(
                    "Активный салон не найден."
                )

            master = db.scalar(
                select(Master)
                .options(
                    joinedload(Master.user)
                )
                .where(
                    Master.id == master_id,
                    Master.salon_id == salon.id,
                )
            )

            if master is None:
                raise ValueError(
                    "Мастер больше не относится "
                    "к вашему салону."
                )

            if (
                master.user is None
                or not master.user.is_active
            ):
                raise ValueError(
                    "Аккаунт мастера отключён."
                )

            branches = list(
                db.scalars(
                    select(Branch)
                    .where(
                        Branch.salon_id == salon.id
                    )
                    .order_by(Branch.id)
                ).all()
            )

            if not branches:
                raise ValueError(
                    "В салоне нет филиалов."
                )

            context.user_data[
                "branch_assignment_master_id"
            ] = master.id
            context.user_data[
                "branch_assignment"
            ] = "branch"

            await update.message.reply_text(
                "Шаг 2 из 2. Выберите филиал:",
                reply_markup=branches_for_master_menu(
                    branches
                ),
            )
            return True

        except ValueError as error:
            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=user_main_menu(
                    db,
                    owner if "owner" in locals() else None,
                    update.effective_user.id,
                ),
            )
            return True

        except Exception:
            db.rollback()
            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                "❌ Не удалось загрузить филиалы.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        finally:
            db.close()

    if stage == "branch":
        if (
            not text_value.startswith("🏬 ")
            or "#" not in text_value
        ):
            await update.message.reply_text(
                "Выберите филиал с помощью кнопки."
            )
            return True

        try:
            branch_id = int(
                text_value.rsplit("#", 1)[1]
            )
        except ValueError:
            await update.message.reply_text(
                "Не удалось определить филиал."
            )
            return True

        master_id = context.user_data.get(
            "branch_assignment_master_id"
        )

        if master_id is None:
            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                "Сначала выберите мастера.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        db = SessionLocal()

        try:
            # Блокируем владельца и салон, чтобы
            # назначение не пересеклось с удалением
            # мастера/филиала в другом запросе.
            owner = db.scalar(
                select(User)
                .where(
                    User.telegram_id
                    == update.effective_user.id
                )
                .with_for_update()
            )

            if (
                owner is None
                or not owner.is_active
            ):
                raise ValueError(
                    "Пользователь не найден или отключён."
                )

            salon = db.scalar(
                select(Salon)
                .where(
                    Salon.owner_id == owner.id,
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

            master = db.scalar(
                select(Master)
                .options(
                    joinedload(Master.user),
                    joinedload(Master.branch),
                )
                .where(
                    Master.id == master_id,
                    Master.salon_id == salon.id,
                )
                .with_for_update()
            )

            if master is None:
                raise ValueError(
                    "Мастер больше не относится "
                    "к вашему салону."
                )

            if (
                master.user is None
                or not master.user.is_active
            ):
                raise ValueError(
                    "Аккаунт мастера отключён."
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
                    "Филиал не найден или уже удалён."
                )

            if master.branch_id == branch.id:
                master_name = (
                    master.user.first_name
                    if master.user
                    and master.user.first_name
                    else f"#{master.id}"
                )

                clear_branch_assignment(
                    context
                )

                await update.message.reply_text(
                    "ℹ️ Этот филиал уже назначен мастеру.\n\n"
                    f"Мастер: {master_name}\n"
                    f"Филиал: {branch.name}",
                    reply_markup=user_main_menu(
                        db,
                        owner,
                        update.effective_user.id,
                    ),
                )
                return True

            master.branch_id = branch.id
            db.add(master)
            db.commit()

            master_name = (
                master.user.first_name
                if master.user
                and master.user.first_name
                else f"#{master.id}"
            )
            branch_name = branch.name

            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                "✅ Филиал назначен!\n\n"
                f"Мастер: {master_name}\n"
                f"Филиал: {branch_name}",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            return True

        except ValueError as error:
            db.rollback()
            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=user_main_menu(
                    db,
                    owner if "owner" in locals() else None,
                    update.effective_user.id,
                ),
            )
            return True

        except Exception:
            db.rollback()
            clear_branch_assignment(
                context
            )

            await update.message.reply_text(
                "❌ Не удалось назначить филиал мастеру.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )
            return True

        finally:
            db.close()

    clear_branch_assignment(
        context
    )
    return False
