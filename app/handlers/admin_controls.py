from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.admin_panel import admin_menu
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.salon import Salon
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
        # Платформенных владельца/админов не выводим
        # в обычные кнопки блокировки.
        if is_platform_admin(
            user.telegram_id
        ):
            continue

        button_text = (
            f"⛔ Заблокировать пользователя #{user.id}"
            if user.is_active
            else f"✅ Разблокировать пользователя #{user.id}"
        )

        keyboard.append(
            [KeyboardButton(button_text)]
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
        button_text = (
            f"↩️ Снять проверку мастера #{master.id}"
            if master.is_verified
            else f"✅ Подтвердить мастера #{master.id}"
        )

        keyboard.append(
            [KeyboardButton(button_text)]
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
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    await update.message.reply_text(
        "⛔ У вас нет доступа к управлению SaaS-платформой.",
        reply_markup=main_menu(
            role=role,
            telegram_id=update.effective_user.id,
        ),
    )


def disable_user_booking_access(
    db,
    target_user: User,
) -> None:
    # Если пользователь сам является мастером —
    # сразу выключаем приём записей.
    db.execute(
        update(Master)
        .where(
            Master.user_id == target_user.id,
            Master.booking_enabled.is_(True),
        )
        .values(
            booking_enabled=False
        )
    )

    # Если пользователь владеет салоном —
    # отключаем приём записей у всех мастеров его салонов.
    salon_ids = list(
        db.scalars(
            select(Salon.id).where(
                Salon.owner_id == target_user.id
            )
        ).all()
    )

    if salon_ids:
        db.execute(
            update(Master)
            .where(
                Master.salon_id.in_(
                    salon_ids
                ),
                Master.booking_enabled.is_(True),
            )
            .values(
                booking_enabled=False
            )
        )


async def change_user_active_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    is_active: bool,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
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

        if is_platform_owner(
            target_user.telegram_id
        ):
            await update.message.reply_text(
                "⛔ Главного владельца платформы блокировать нельзя.",
                reply_markup=admin_menu(),
            )
            return

        if (
            is_platform_admin(
                target_user.telegram_id
            )
            and not can_manage_admins(
                admin
            )
        ):
            await update.message.reply_text(
                "⛔ Только главный владелец платформы "
                "может управлять администраторами.",
                reply_markup=admin_menu(),
            )
            return

        if target_user.is_active == is_active:
            await update.message.reply_text(
                (
                    "ℹ️ Пользователь уже разблокирован."
                    if is_active
                    else "ℹ️ Пользователь уже заблокирован."
                ),
                reply_markup=admin_menu(),
            )
            return

        target_user.is_active = is_active
        db.add(target_user)

        if not is_active:
            disable_user_booking_access(
                db,
                target_user,
            )

        db.commit()

        action_text = (
            "разблокирован"
            if is_active
            else "заблокирован"
        )

        await update.message.reply_text(
            f"✅ Пользователь #{user_id} {action_text}.",
            reply_markup=admin_menu(),
        )

        try:
            await context.bot.send_message(
                chat_id=target_user.telegram_id,
                text=(
                    "✅ Ваш аккаунт GlowFlow снова активен."
                    if is_active
                    else (
                        "⛔ Ваш аккаунт GlowFlow временно отключён "
                        "администратором.\n\n"
                        "Приём новых записей автоматически выключен."
                    )
                ),
            )
        except Exception:
            pass

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
    if (
        update.message is None
        or update.effective_user is None
    ):
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
            select(Master)
            .options(
                joinedload(
                    Master.user
                )
            )
            .where(
                Master.id == master_id
            )
        )

        if master is None:
            await update.message.reply_text(
                "❌ Мастер не найден.",
                reply_markup=admin_menu(),
            )
            return

        if master.user is None:
            await update.message.reply_text(
                "❌ У мастера отсутствует пользователь.",
                reply_markup=admin_menu(),
            )
            return

        if is_verified and not master.user.is_active:
            await update.message.reply_text(
                "⛔ Нельзя подтвердить мастера: "
                "его пользовательский аккаунт отключён.",
                reply_markup=admin_menu(),
            )
            return

        if master.is_verified == is_verified:
            await update.message.reply_text(
                (
                    "ℹ️ Мастер уже подтверждён."
                    if is_verified
                    else "ℹ️ Проверка мастера уже снята."
                ),
                reply_markup=admin_menu(),
            )
            return

        master.is_verified = is_verified

        # Верификация сама по себе не включает запись:
        # мастер должен пройти проверки готовности
        # через «✅ Включить запись».
        if not is_verified:
            master.booking_enabled = False

        db.add(master)
        db.commit()

        await update.message.reply_text(
            (
                f"✅ Мастер #{master_id} подтверждён."
                if is_verified
                else (
                    f"✅ Проверка мастера #{master_id} снята. "
                    "Приём записей выключен."
                )
            ),
            reply_markup=admin_menu(),
        )

        try:
            await context.bot.send_message(
                chat_id=master.user.telegram_id,
                text=(
                    "✅ Ваш профиль мастера GlowFlow подтверждён!\n\n"
                    "Теперь, когда город, услуги и вся неделя "
                    "расписания настроены, вы можете нажать "
                    "«✅ Включить запись»."
                    if is_verified
                    else (
                        "↩️ Проверка вашего профиля мастера GlowFlow "
                        "снята администратором.\n\n"
                        "Приём новых записей автоматически выключен."
                    )
                ),
            )
        except Exception:
            pass

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить статус мастера.",
            reply_markup=admin_menu(),
        )

    finally:
        db.close()
