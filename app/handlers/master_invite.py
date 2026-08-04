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
from app.services.subscription_access import require_active_salon_access
from app.services.subscription_limits import can_add_master


def master_invite_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("❌ Отменить приглашение мастера")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите Telegram ID мастера",
    )


def clear_master_invite(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "master_invite",
        "invited_telegram_id",
    ):
        context.user_data.pop(key, None)


async def begin_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        owner = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if owner is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start.",
                reply_markup=main_menu(),
            )
            return

        if owner.role not in {"owner", "admin"}:
            await update.message.reply_text(
                "⛔ Приглашать мастеров может только владелец салона.",
                reply_markup=main_menu(role=owner.role),
            )
            return

        salon = db.scalar(
            select(Salon).where(
                Salon.owner_id == owner.id,
                Salon.is_active.is_(True),
            )
        )

        if salon is None:
            await update.message.reply_text(
                "❌ Активный салон не найден.",
                reply_markup=main_menu(role=owner.role),
            )
            return

        require_active_salon_access(salon)

        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            await update.message.reply_text(
                "⛔ Лимит тарифа достигнут.\n\n"
                f"{reason}",
                reply_markup=main_menu(role=owner.role),
            )
            return

    finally:
        db.close()

    clear_master_invite(context)
    context.user_data["master_invite"] = "telegram_id"

    await update.message.reply_text(
        "🧑‍💼 Приглашение мастера\n\n"
        "Введите Telegram ID пользователя, которого хотите добавить.\n\n"
        "Пользователь должен хотя бы один раз отправить /start вашему боту.",
        reply_markup=master_invite_menu(),
    )


async def process_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get("master_invite")

    if stage is None:
        return False

    if update.message is None or update.message.text is None:
        return False

    text = update.message.text.strip()

    if text == "❌ Отменить приглашение мастера":
        clear_master_invite(context)

        await update.message.reply_text(
            "❌ Приглашение мастера отменено.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return True

    if stage == "telegram_id":
        try:
            telegram_id = int(text)
        except ValueError:
            await update.message.reply_text(
                "Введите Telegram ID цифрами."
            )
            return True

        db = SessionLocal()

        try:
            owner = db.scalar(
                select(User).where(
                    User.telegram_id == update.effective_user.id
                )
            )

            if owner is None:
                raise ValueError(
                    "Владелец не найден. Отправьте /start."
                )

            if owner.role not in {"owner", "admin"}:
                raise ValueError(
                    "У вас нет доступа к приглашению мастеров."
                )

            salon = db.scalar(
                select(Salon).where(
                    Salon.owner_id == owner.id,
                    Salon.is_active.is_(True),
                )
            )

            if salon is None:
                raise ValueError(
                    "Активный салон не найден."
                )

            require_active_salon_access(salon)

            allowed, reason = can_add_master(
                db,
                salon,
            )

            if not allowed:
                raise ValueError(reason)

            invited_user = db.scalar(
                select(User).where(
                    User.telegram_id == telegram_id
                )
            )

            if invited_user is None:
                raise ValueError(
                    "Пользователь с таким Telegram ID не найден. "
                    "Попросите его сначала отправить /start боту."
                )

            master = db.scalar(
                select(Master).where(
                    Master.user_id == invited_user.id
                )
            )

            if master is None:
                master = Master(
                    user_id=invited_user.id,
                    salon_id=salon.id,
                    description="Мастер салона",
                    slug=f"master-{invited_user.telegram_id}",
                    rating=5.0,
                    booking_enabled=False,
                    is_verified=False,
                )
                db.add(master)
            else:
                if master.salon_id == salon.id:
                    raise ValueError(
                        "Этот мастер уже добавлен в ваш салон."
                    )

                if master.salon_id is not None:
                    raise ValueError(
                        "Этот мастер уже состоит в другом салоне."
                    )

                master.salon_id = salon.id
                master.booking_enabled = False

            main_branch = db.scalar(
                select(Branch)
                .where(Branch.salon_id == salon.id)
                .order_by(Branch.id)
            )

            if main_branch is not None:
                master.branch_id = main_branch.id

            # Не перезаписываем системного администратора
            # или владельца собственного салона.
            if (
                not is_platform_admin(invited_user.telegram_id)
                and invited_user.role != "owner"
            ):
                invited_user.role = "master"

            db.add(invited_user)
            db.add(master)
            db.commit()
            db.refresh(master)

            master_id = master.id
            master_name = invited_user.first_name
            branch_name = (
                main_branch.name
                if main_branch
                else "не назначен"
            )

        except ValueError as error:
            db.rollback()
            clear_master_invite(context)

            await update.message.reply_text(
                f"❌ {error}",
                reply_markup=main_menu(
                role=owner.role,
                telegram_id=owner.telegram_id,
                has_salon=True,
            ),
            )
            return True

        except Exception:
            db.rollback()
            clear_master_invite(context)

            await update.message.reply_text(
                "❌ Не удалось добавить мастера.",
                reply_markup=main_menu(
                role=owner.role,
                telegram_id=owner.telegram_id,
                has_salon=True,
            ),
            )
            return True

        finally:
            db.close()

        clear_master_invite(context)

        await update.message.reply_text(
            "✅ Мастер добавлен в салон!\n\n"
            f"ID мастера: {master_id}\n"
            f"Имя: {master_name}\n"
            f"Филиал: {branch_name}",
            reply_markup=main_menu(
                role=owner.role,
                telegram_id=owner.telegram_id,
                has_salon=True,
            ),
        )
        return True

    return False
