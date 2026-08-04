from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.admin_panel import admin_menu
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.user import User
from app.services.access_control import (
    can_manage_admins,
    can_manage_platform,
    is_platform_admin,
    is_platform_owner,
)


def admin_users_actions_menu(
    users: list[User],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for user in users:
        # Системных владельца и администраторов не показываем
        # в обычных кнопках блокировки.
        if is_platform_admin(user.telegram_id):
            continue

        if user.is_active:
            keyboard.append(
                [
                    KeyboardButton(
                        f"⛔ Заблокировать пользователя #{user.id}"
                    )
                ]
            )
        else:
            keyboard.append(
                [
                    KeyboardButton(
                        f"✅ Разблокировать пользователя #{user.id}"
                    )
                ]
            )

    keyboard.extend(
        [
            [KeyboardButton("👑 Админ-панель")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление пользователями",
    )


def admin_masters_actions_menu(
    masters: list[Master],
) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []

    for master in masters:
        if not master.is_verified:
            keyboard.append(
                [
                    KeyboardButton(
                        f"✅ Подтвердить мастера #{master.id}"
                    )
                ]
            )
        else:
            keyboard.append(
                [
                    KeyboardButton(
                        f"↩️ Снять проверку мастера #{master.id}"
                    )
                ]
            )

    keyboard.extend(
        [
            [KeyboardButton("👑 Админ-панель")],
            [KeyboardButton("⬅️ Назад")],
        ]
    )

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Управление мастерами",
    )


def get_platform_admin(
    db,
    telegram_id: int,
) -> User | None:
    user = db.scalar(
        select(User).where(
            User.telegram_id == telegram_id
        )
    )

    if not can_manage_platform(user):
        return None

    return user


async def deny_access(
    update: Update,
    role: str | None = None,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению SaaS-платформой.",
        reply_markup=main_menu(
            role=role,
            telegram_id=update.effective_user.id,
        ),
    )


async def change_user_active_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    is_active: bool,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        target_user = db.scalar(
            select(User).where(
                User.id == user_id
            )
        )

        if target_user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден.",
                reply_markup=admin_menu(),
            )
            return

        if target_user.id == admin.id:
            await update.message.reply_text(
                "⛔ Нельзя заблокировать собственный аккаунт.",
                reply_markup=admin_menu(),
            )
            return

        if is_platform_owner(target_user.telegram_id):
            await update.message.reply_text(
                "⛔ Главного владельца платформы блокировать нельзя.",
                reply_markup=admin_menu(),
            )
            return

        if (
            is_platform_admin(target_user.telegram_id)
            and not can_manage_admins(admin)
        ):
            await update.message.reply_text(
                "⛔ Только главный владелец платформы "
                "может управлять администраторами.",
                reply_markup=admin_menu(),
            )
            return

        target_user.is_active = is_active

        if target_user.master is not None and not is_active:
            target_user.master.booking_enabled = False

        db.commit()

        action = (
            "разблокирован"
            if is_active
            else "заблокирован"
        )

        await update.message.reply_text(
            f"✅ Пользователь #{user_id} {action}.",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус пользователя.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()


async def change_master_verified_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    master_id: int,
    is_verified: bool,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        admin = get_platform_admin(
            db,
            update.effective_user.id,
        )

        if admin is None:
            await deny_access(update)
            return

        master = db.scalar(
            select(Master).where(
                Master.id == master_id
            )
        )

        if master is None:
            await update.message.reply_text(
                "❌ Мастер не найден.",
                reply_markup=admin_menu(),
            )
            return

        master.is_verified = is_verified

        if not is_verified:
            master.booking_enabled = False

        db.commit()

        action = (
            "подтверждён"
            if is_verified
            else "снят с проверки"
        )

        await update.message.reply_text(
            f"✅ Мастер #{master_id} {action}.",
            reply_markup=admin_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус мастера.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()
