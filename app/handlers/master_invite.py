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
    owner: User,
) -> Salon | None:
    return db.scalar(
        select(Salon).where(
            Salon.owner_id == owner.id,
            Salon.is_active.is_(True),
        )
    )


def owner_main_menu(
    db,
    owner: User,
    *,
    has_salon: bool,
) -> ReplyKeyboardMarkup:
    has_master = (
        db.scalar(
            select(Master.id)
            .where(
                Master.user_id == owner.id
            )
            .limit(1)
        )
        is not None
    )

    return main_menu(
        role=owner.role,
        telegram_id=owner.telegram_id,
        has_salon=has_salon,
        has_master=has_master,
    )


async def begin_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        owner = get_user(
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
                "❌ Ваш аккаунт временно отключён.",
                reply_markup=owner_main_menu(
                    db,
                    owner,
                    has_salon=False,
                ),
            )
            return

        salon = get_owned_salon(
            db,
            owner,
        )

        if salon is None:
            await update.message.reply_text(
                "⛔ Приглашать мастеров может только "
                "владелец активного салона.",
                reply_markup=owner_main_menu(
                    db,
                    owner,
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
                reply_markup=owner_main_menu(
                    db,
                    owner,
                    has_salon=True,
                ),
            )
            return

        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            await update.message.reply_text(
                "⛔ Лимит тарифа достигнут.\n\n"
                f"{reason}\n\n"
                "Откройте «💳 Тариф и подписка», "
                "чтобы выбрать другой тариф.",
                reply_markup=owner_main_menu(
                    db,
                    owner,
                    has_salon=True,
                ),
            )
            return

        clear_master_invite(
            context
        )
        context.user_data[
            "master_invite"
        ] = "telegram_id"

        await update.message.reply_text(
            "🧑‍💼 Добавление мастера\n\n"
            "Введите Telegram ID пользователя.\n\n"
            "Он должен хотя бы один раз отправить /start боту.\n"
            "После добавления приём записей будет выключен "
            "до проверки и настройки профиля.",
            reply_markup=master_invite_menu(),
        )

    finally:
        db.close()


async def process_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    stage = context.user_data.get(
        "master_invite"
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

    if text == "❌ Отменить приглашение мастера":
        clear_master_invite(
            context
        )

        db = SessionLocal()

        try:
            owner = get_user(
                db,
                update.effective_user.id,
            )

            if owner is not None:
                salon = get_owned_salon(
                    db,
                    owner,
                )
                reply_markup = owner_main_menu(
                    db,
                    owner,
                    has_salon=salon is not None,
                )
            else:
                reply_markup = main_menu(
                    telegram_id=update.effective_user.id,
                )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Добавление мастера отменено.",
            reply_markup=reply_markup,
        )
        return True

    if stage != "telegram_id":
        return False

    try:
        telegram_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "Введите Telegram ID только цифрами."
        )
        return True

    if telegram_id <= 0:
        await update.message.reply_text(
            "❌ Telegram ID должен быть положительным числом."
        )
        return True

    db = SessionLocal()

    try:
        owner = get_user(
            db,
            update.effective_user.id,
        )

        if owner is None:
            raise ValueError(
                "Владелец не найден. Отправьте /start."
            )

        if not owner.is_active:
            raise ValueError(
                "Ваш аккаунт временно отключён."
            )

        salon = get_owned_salon(
            db,
            owner,
        )

        if salon is None:
            raise ValueError(
                "Активный салон не найден."
            )

        require_active_salon_access(
            salon
        )

        # Повторная проверка лимита непосредственно
        # перед изменением базы.
        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            raise ValueError(
                reason
            )

        invited_user = get_user(
            db,
            telegram_id,
        )

        if invited_user is None:
            raise ValueError(
                "Пользователь с таким Telegram ID не найден. "
                "Попросите его сначала отправить /start боту."
            )

        if not invited_user.is_active:
            raise ValueError(
                "Этот пользователь сейчас отключён администратором."
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
                description="Мастер салона GlowFlow",
                slug=f"master-{invited_user.telegram_id}",
                rating=5.0,
                booking_enabled=False,
                is_verified=False,
            )
            db.add(master)
            db.flush()
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

            # После присоединения к салону запись
            # включается вручную только после проверки готовности.
            master.booking_enabled = False
            db.add(master)

        main_branch = db.scalar(
            select(Branch)
            .where(
                Branch.salon_id == salon.id
            )
            .order_by(Branch.id)
            .limit(1)
        )

        if main_branch is not None:
            master.branch_id = main_branch.id

        # Не ломаем роли владельца салона и платформенного админа.
        if (
            invited_user.role == "client"
            and not is_platform_admin(
                invited_user.telegram_id
            )
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
            if main_branch is not None
            else "не назначен"
        )
        invited_id = invited_user.telegram_id

        reply_markup = owner_main_menu(
            db,
            owner,
            has_salon=True,
        )

    except ValueError as error:
        db.rollback()
        clear_master_invite(
            context
        )

        owner = get_user(
            db,
            update.effective_user.id,
        )

        if owner is not None:
            salon = get_owned_salon(
                db,
                owner,
            )
            reply_markup = owner_main_menu(
                db,
                owner,
                has_salon=salon is not None,
            )
        else:
            reply_markup = main_menu(
                telegram_id=update.effective_user.id,
            )

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=reply_markup,
        )
        return True

    except Exception:
        db.rollback()
        clear_master_invite(
            context
        )

        await update.message.reply_text(
            "❌ Не удалось добавить мастера. Попробуйте позже.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return True

    finally:
        db.close()

    clear_master_invite(
        context
    )

    await update.message.reply_text(
        "✅ Мастер добавлен в салон!\n\n"
        f"ID мастера: {master_id}\n"
        f"Имя: {master_name}\n"
        f"Филиал: {branch_name}\n"
        "Приём записей: выключен\n\n"
        "Мастеру нужно настроить профиль и услуги, "
        "после чего запись можно включить.",
        reply_markup=reply_markup,
    )

    try:
        await context.bot.send_message(
            chat_id=invited_id,
            text=(
                f"🏢 Вас добавили в салон «{salon.name}» в GlowFlow.\n\n"
                "Откройте «💼 Кабинет мастера», "
                "настройте город, услуги и расписание.\n"
                "Приём записей пока выключен."
            ),
        )
    except Exception:
        pass

    return True
