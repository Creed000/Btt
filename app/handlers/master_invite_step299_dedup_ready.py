from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.master import Master
from app.models.master_salon_invite import MasterSalonInvite
from app.models.salon import Salon
from app.models.user import User
from app.services.access_control import is_platform_admin
from app.services.subscription_access import require_active_salon_access
from app.services.subscription_limits import can_add_master
from app.services.timezone import local_naive_now


def master_invite_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("❌ Отменить приглашение мастера")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Введите Telegram ID мастера",
    )


def invite_response_menu(
    invite_id: int,
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    f"✅ Принять приглашение #{invite_id}"
                )
            ],
            [
                KeyboardButton(
                    f"❌ Отклонить приглашение #{invite_id}"
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Приглашение в салон",
    )


def clear_master_invite(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "master_invite",
        "invited_telegram_id",
    ):
        context.user_data.pop(key, None)


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


async def begin_master_invite(
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

        require_active_salon_access(
            salon
        )

        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            await update.message.reply_text(
                "⛔ Лимит тарифа достигнут.\n\n"
                f"{reason}",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
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
            "🧑‍💼 Приглашение мастера\n\n"
            "Введите Telegram ID пользователя.\n\n"
            "Пользователь должен хотя бы один раз "
            "отправить /start этому боту.\n"
            "Мастер будет добавлен только после "
            "его подтверждения.",
            reply_markup=master_invite_menu(),
        )

    except ValueError as error:
        await update.message.reply_text(
            f"⛔ {error}",
            reply_markup=user_main_menu(
                db,
                owner if "owner" in locals() else None,
                update.effective_user.id,
            ),
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

    text_value = update.message.text.strip()

    if text_value == "❌ Отменить приглашение мастера":
        clear_master_invite(
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
            "❌ Приглашение мастера отменено.",
            reply_markup=reply_markup,
        )
        return True

    if stage != "telegram_id":
        clear_master_invite(
            context
        )
        return False

    try:
        telegram_id = int(
            text_value
        )
    except ValueError:
        await update.message.reply_text(
            "Введите Telegram ID цифрами."
        )
        return True

    db = SessionLocal()

    try:
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
                "Владелец не найден или отключён."
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

        require_active_salon_access(
            salon
        )

        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            raise ValueError(
                reason
            )

        invited_user = db.scalar(
            select(User)
            .where(
                User.telegram_id == telegram_id
            )
            .with_for_update()
        )

        if invited_user is None:
            raise ValueError(
                "Пользователь с таким Telegram ID не найден. "
                "Попросите его сначала отправить /start боту."
            )

        if not invited_user.is_active:
            raise ValueError(
                "Аккаунт этого пользователя отключён."
            )

        master = db.scalar(
            select(Master)
            .where(
                Master.user_id == invited_user.id
            )
            .with_for_update()
        )

        if (
            master is not None
            and master.salon_id == salon.id
        ):
            raise ValueError(
                "Этот мастер уже состоит в вашем салоне."
            )

        if (
            master is not None
            and master.salon_id is not None
            and master.salon_id != salon.id
        ):
            raise ValueError(
                "Этот мастер уже состоит в другом салоне."
            )

        existing_invite = db.scalar(
            select(MasterSalonInvite)
            .where(
                MasterSalonInvite.salon_id == salon.id,
                MasterSalonInvite.invited_user_id
                == invited_user.id,
                MasterSalonInvite.status == "pending",
            )
            .order_by(
                MasterSalonInvite.id.desc()
            )
            .limit(1)
        )

        if existing_invite is not None:
            raise ValueError(
                f"Приглашение #{existing_invite.id} "
                "уже ожидает ответа мастера."
            )

        invite = MasterSalonInvite(
            salon_id=salon.id,
            invited_user_id=invited_user.id,
            invited_by_user_id=owner.id,
            status="pending",
        )

        db.add(invite)
        db.flush()

        invite_id = invite.id
        salon_name = salon.name
        invited_name = (
            invited_user.first_name
            or f"Telegram ID {invited_user.telegram_id}"
        )
        invited_telegram_id = invited_user.telegram_id

        db.commit()

        clear_master_invite(
            context
        )

        await update.message.reply_text(
            "✅ Приглашение отправлено.\n\n"
            f"Приглашение: #{invite_id}\n"
            f"Мастер: {invited_name}\n"
            f"Салон: {salon_name}\n\n"
            "Мастер будет добавлен только после "
            "нажатия «✅ Принять».",
            reply_markup=user_main_menu(
                db,
                owner,
                update.effective_user.id,
            ),
        )

        try:
            await context.bot.send_message(
                chat_id=invited_telegram_id,
                text=(
                    "🏢 Вас приглашают в салон GlowFlow.\n\n"
                    f"Салон: {salon_name}\n"
                    f"Приглашение: #{invite_id}\n\n"
                    "Примите или отклоните приглашение."
                ),
                reply_markup=invite_response_menu(
                    invite_id
                ),
            )
        except Exception:
            # Запрос уже сохранён. Ошибка доставки
            # не должна удалять приглашение.
            pass

        return True

    except ValueError as error:
        db.rollback()
        clear_master_invite(
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

    except IntegrityError:
        db.rollback()
        clear_master_invite(
            context
        )

        # Уникальный индекс — последняя защита от
        # двух почти одновременных приглашений.
        try:
            owner, salon = get_owner_and_salon(
                db,
                update.effective_user.id,
            )

            invited_user = db.scalar(
                select(User).where(
                    User.telegram_id == telegram_id
                )
            )

            existing_invite = None

            if (
                salon is not None
                and invited_user is not None
            ):
                existing_invite = db.scalar(
                    select(MasterSalonInvite)
                    .where(
                        MasterSalonInvite.salon_id
                        == salon.id,
                        MasterSalonInvite.invited_user_id
                        == invited_user.id,
                        MasterSalonInvite.status
                        == "pending",
                    )
                    .order_by(
                        MasterSalonInvite.id.desc()
                    )
                    .limit(1)
                )

            if existing_invite is not None:
                await update.message.reply_text(
                    "ℹ️ Приглашение уже отправлено "
                    "и ожидает ответа мастера.\n\n"
                    f"Приглашение: #{existing_invite.id}",
                    reply_markup=user_main_menu(
                        db,
                        owner,
                        update.effective_user.id,
                    ),
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось отправить приглашение. "
                    "Попробуйте ещё раз.",
                    reply_markup=user_main_menu(
                        db,
                        owner,
                        update.effective_user.id,
                    ),
                )

        except Exception:
            db.rollback()

            await update.message.reply_text(
                "❌ Не удалось отправить приглашение.",
                reply_markup=main_menu(
                    telegram_id=update.effective_user.id,
                ),
            )

        return True

    except Exception:
        db.rollback()
        clear_master_invite(
            context
        )

        await update.message.reply_text(
            "❌ Не удалось отправить приглашение.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )
        return True

    finally:
        db.close()


async def accept_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    invite_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        invited_user = db.scalar(
            select(User)
            .where(
                User.telegram_id
                == update.effective_user.id
            )
            .with_for_update()
        )

        if (
            invited_user is None
            or not invited_user.is_active
        ):
            raise ValueError(
                "Ваш аккаунт не найден или отключён."
            )

        invite = db.scalar(
            select(MasterSalonInvite)
            .options(
                joinedload(
                    MasterSalonInvite.salon
                ),
                joinedload(
                    MasterSalonInvite.invited_by
                ),
            )
            .where(
                MasterSalonInvite.id == invite_id,
                MasterSalonInvite.invited_user_id
                == invited_user.id,
            )
            .with_for_update()
        )

        if invite is None:
            raise ValueError(
                "Приглашение не найдено."
            )

        if invite.status != "pending":
            raise ValueError(
                f"Приглашение уже обработано "
                f"(статус: {invite.status})."
            )

        salon = db.scalar(
            select(Salon)
            .where(
                Salon.id == invite.salon_id,
                Salon.is_active.is_(True),
            )
            .with_for_update()
        )

        if salon is None:
            invite.status = "expired"
            invite.resolved_at = local_naive_now()
            db.add(invite)
            db.commit()

            raise ValueError(
                "Салон больше недоступен."
            )

        require_active_salon_access(
            salon
        )

        allowed, reason = can_add_master(
            db,
            salon,
        )

        if not allowed:
            raise ValueError(
                "Сейчас приглашение нельзя принять: "
                f"{reason}"
            )

        master = db.scalar(
            select(Master)
            .where(
                Master.user_id == invited_user.id
            )
            .with_for_update()
        )

        if (
            master is not None
            and master.salon_id is not None
            and master.salon_id != salon.id
        ):
            raise ValueError(
                "Вы уже состоите в другом салоне."
            )

        main_branch = db.scalar(
            select(Branch)
            .where(
                Branch.salon_id == salon.id
            )
            .order_by(Branch.id.asc())
            .limit(1)
        )

        if master is None:
            master = Master(
                user_id=invited_user.id,
                salon_id=salon.id,
                branch_id=(
                    main_branch.id
                    if main_branch is not None
                    else None
                ),
                description="Мастер салона",
                slug=f"master-{invited_user.telegram_id}",
                rating=5.0,
                booking_enabled=False,
                is_verified=False,
            )
            db.add(master)
        else:
            master.salon_id = salon.id
            master.branch_id = (
                main_branch.id
                if main_branch is not None
                else None
            )
            # После смены контекста мастер должен
            # повторно проверить расписание/услуги.
            master.booking_enabled = False
            db.add(master)

        # Не уничтожаем бизнес-роль владельца.
        # Системные админы тоже не зависят от role.
        if (
            invited_user.role == "client"
            and not is_platform_admin(
                invited_user.telegram_id
            )
        ):
            invited_user.role = "master"

        resolved_at = local_naive_now()

        invite.status = "accepted"
        invite.resolved_at = resolved_at

        # После вступления в салон остальные старые
        # pending-приглашения этому мастеру закрываются.
        db.execute(
            update(MasterSalonInvite)
            .where(
                MasterSalonInvite.invited_user_id
                == invited_user.id,
                MasterSalonInvite.id != invite.id,
                MasterSalonInvite.status == "pending",
            )
            .values(
                status="expired",
                resolved_at=resolved_at,
            )
        )

        db.add(invited_user)
        db.add(invite)
        db.flush()

        master_id = master.id
        owner_telegram_id = (
            invite.invited_by.telegram_id
            if invite.invited_by is not None
            else None
        )
        salon_name = salon.name

        db.commit()

        await update.message.reply_text(
            "✅ Приглашение принято.\n\n"
            f"Салон: {salon_name}\n"
            f"ID мастера: {master_id}\n\n"
            "Приём новых записей пока выключен. "
            "Проверьте филиал, услуги и расписание "
            "в кабинете мастера.",
            reply_markup=main_menu(
                role=invited_user.role,
                telegram_id=update.effective_user.id,
                has_salon=(
                    db.scalar(
                        select(Salon.id)
                        .where(
                            Salon.owner_id
                            == invited_user.id,
                            Salon.is_active.is_(True),
                        )
                        .limit(1)
                    )
                    is not None
                ),
                has_master=True,
            ),
        )

        if owner_telegram_id is not None:
            try:
                await context.bot.send_message(
                    chat_id=owner_telegram_id,
                    text=(
                        "✅ Мастер принял приглашение.\n\n"
                        f"Салон: {salon_name}\n"
                        f"Мастер ID: {master_id}"
                    ),
                )
            except Exception:
                pass

    except ValueError as error:
        db.rollback()

        user = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                user,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось принять приглашение.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def decline_master_invite(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    invite_id: int,
) -> None:
    if (
        update.message is None
        or update.effective_user is None
    ):
        return

    db = SessionLocal()

    try:
        invited_user = db.scalar(
            select(User)
            .where(
                User.telegram_id
                == update.effective_user.id
            )
            .with_for_update()
        )

        if invited_user is None:
            raise ValueError(
                "Пользователь не найден."
            )

        invite = db.scalar(
            select(MasterSalonInvite)
            .options(
                joinedload(
                    MasterSalonInvite.salon
                ),
                joinedload(
                    MasterSalonInvite.invited_by
                ),
            )
            .where(
                MasterSalonInvite.id == invite_id,
                MasterSalonInvite.invited_user_id
                == invited_user.id,
            )
            .with_for_update()
        )

        if invite is None:
            raise ValueError(
                "Приглашение не найдено."
            )

        if invite.status != "pending":
            raise ValueError(
                f"Приглашение уже обработано "
                f"(статус: {invite.status})."
            )

        invite.status = "declined"
        invite.resolved_at = local_naive_now()

        salon_name = (
            invite.salon.name
            if invite.salon is not None
            else f"Салон #{invite.salon_id}"
        )

        owner_telegram_id = (
            invite.invited_by.telegram_id
            if invite.invited_by is not None
            else None
        )

        db.add(invite)
        db.commit()

        await update.message.reply_text(
            "❌ Приглашение отклонено.\n\n"
            f"Салон: {salon_name}",
            reply_markup=user_main_menu(
                db,
                invited_user,
                update.effective_user.id,
            ),
        )

        if owner_telegram_id is not None:
            try:
                await context.bot.send_message(
                    chat_id=owner_telegram_id,
                    text=(
                        "❌ Мастер отклонил приглашение.\n\n"
                        f"Салон: {salon_name}\n"
                        f"Telegram ID: {invited_user.telegram_id}"
                    ),
                )
            except Exception:
                pass

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                invited_user if "invited_user" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось отклонить приглашение.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def master_invite_response_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if (
        update.message is None
        or update.message.text is None
    ):
        return

    text_value = update.message.text.strip()

    accept_prefix = "✅ Принять приглашение #"

    if text_value.startswith(
        accept_prefix
    ):
        raw_id = text_value.removeprefix(
            accept_prefix
        ).strip()

        if raw_id.isdigit():
            await accept_master_invite(
                update,
                context,
                int(raw_id),
            )
        return

    decline_prefix = "❌ Отклонить приглашение #"

    if text_value.startswith(
        decline_prefix
    ):
        raw_id = text_value.removeprefix(
            decline_prefix
        ).strip()

        if raw_id.isdigit():
            await decline_master_invite(
                update,
                context,
                int(raw_id),
            )


master_invite_response_handler = MessageHandler(
    filters.Regex(
        r"^(✅ Принять приглашение #[0-9]+|"
        r"❌ Отклонить приглашение #[0-9]+)$"
    ),
    master_invite_response_router,
)
