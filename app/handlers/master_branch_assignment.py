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

    if owner is None:
        return None, None

    salon = db.scalar(
        select(Salon).where(
            Salon.owner_id == owner.id,
            Salon.is_active.is_(True),
        )
    )

    return owner, salon


async def begin_branch_assignment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
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
                reply_markup=main_menu(),
            )
            return

        if owner.role not in {"owner", "admin"}:
            await update.message.reply_text(
                "⛔ Назначать филиалы может только владелец салона.",
                reply_markup=main_menu(role=owner.role),
            )
            return

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(role=owner.role),
            )
            return

        masters = list(
            db.scalars(
                select(Master)
                .options(joinedload(Master.user))
                .where(
                    Master.salon_id == salon.id
                )
                .order_by(Master.id)
            ).unique().all()
        )

        clear_branch_assignment(context)
        context.user_data["branch_assignment"] = "master"

        await update.message.reply_text(
            "🏬 Назначение филиала мастеру

"
            "Шаг 1 из 2. Выберите мастера:",
            reply_markup=masters_for_branch_menu(masters),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось загрузить мастеров салона.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()


async def process_branch_assignment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("branch_assignment")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить назначение филиала":
        clear_branch_assignment(context)

        await update.message.reply_text(
            "❌ Назначение филиала отменено.",
            reply_markup=main_menu(role="owner"),
        )
        return True

    if text in {
        "Мастеров салона нет",
        "Филиалов салона нет",
    }:
        clear_branch_assignment(context)

        await update.message.reply_text(
            "Для назначения нужны мастер и хотя бы один филиал.",
            reply_markup=main_menu(role="owner"),
        )
        return True

    if stage == "master":
        if not text.startswith("👤 Назначить ") or "#" not in text:
            await update.message.reply_text(
                "Выберите мастера с помощью кнопки."
            )
            return True

        try:
            master_id = int(
                text.rsplit("#", 1)[1]
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

            if owner is None or salon is None:
                raise ValueError(
                    "Активный салон не найден."
                )

            master = db.scalar(
                select(Master).where(
                    Master.id == master_id,
                    Master.salon_id == salon.id,
                )
            )

            if master is None:
                raise ValueError(
                    "Мастер не найден или не принадлежит вашему салону."
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
            clear_branch_assignment(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(role="owner"),
            )
            return True

        finally:
            db.close()

    if stage == "branch":
        if not text.startswith("🏬 ") or "#" not in text:
            await update.message.reply_text(
                "Выберите филиал с помощью кнопки."
            )
            return True

        try:
            branch_id = int(
                text.rsplit("#", 1)[1]
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
            clear_branch_assignment(context)

            await update.message.reply_text(
                "Сначала выберите мастера.",
                reply_markup=main_menu(role="owner"),
            )
            return True

        db = SessionLocal()

        try:
            owner, salon = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            if owner is None or salon is None:
                raise ValueError(
                    "Активный салон не найден."
                )

            master = db.scalar(
                select(Master)
                .options(joinedload(Master.user))
                .where(
                    Master.id == master_id,
                    Master.salon_id == salon.id,
                )
            )

            if master is None:
                raise ValueError(
                    "Мастер не найден."
                )

            branch = db.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.salon_id == salon.id,
                )
            )

            if branch is None:
                raise ValueError(
                    "Филиал не найден или принадлежит другому салону."
                )

            master.branch_id = branch.id
            db.commit()

            master_name = (
                master.user.first_name
                if master.user and master.user.first_name
                else f"#{master.id}"
            )
            branch_name = branch.name

        except ValueError as error:
            db.rollback()
            clear_branch_assignment(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(role="owner"),
            )
            return True

        except Exception:
            db.rollback()
            clear_branch_assignment(context)

            await update.message.reply_text(
                "❌ Не удалось назначить филиал мастеру.",
                reply_markup=main_menu(role="owner"),
            )
            return True

        finally:
            db.close()

        clear_branch_assignment(context)

        await update.message.reply_text(
            "✅ Филиал назначен!

"
            f"Мастер: {master_name}
"
            f"Филиал: {branch_name}",
            reply_markup=main_menu(role="owner"),
        )
        return True

    return False
