from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.branch import Branch
from app.models.master import Master
from app.models.master_invite import MasterInvite
from app.models.salon import Salon
from app.models.user import User
from app.services.subscription_access import (
    require_active_salon_access,
)
from app.services.subscription_limits import (
    can_add_master,
)
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


def clear_master_invite(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    for key in (
        "master_invite",
        "invited_telegram_id",
    ):
        context.user_data.pop(key, None)


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


def invite_decision_menu(
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
            [KeyboardButton("⬅️ Назад")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Приглашение в салон",
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
        owner = db.scalar(
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
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
                "⛔ Ваш аккаунт отключён.",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            return

        salon = db.scalar(
            select(Salon)
            .where(
                Salon.owner_id == owner.id,
                Salon.is_active.is_(True),
            )
            .order_by(Salon.id.asc())
            .limit(1)
        )

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
            "отправить /start вашему боту.\n"
            "Мастер будет добавлен только после "
            "его собственного подтверждения.",
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
            owner = db.scalar(
                select(User).where(
                    User.telegram_id
                    == update.effective_user.id
                )
            )
            reply_markup = user_main_menu(
                db,
                owner,
                update.effective_user.id,
            )
        finally:
            db.close()

        await update.message.reply_text(
            "❌ Приглашение отменено.",
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
            "Введите Telegram ID только цифрами."
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
            select(User).where(
                User.telegram_id == telegram_id
            )
        )

        if (
            invited_user is None
            or not invited_user.is_active
        ):
            raise ValueError(
                "Пользователь не найден или его аккаунт отключён. "
                "Попросите пользователя сначала отправить /start."
            )

        if invited_user.id == owner.id:
            raise ValueError(
                "Нельзя приглашать в салон самого себя."
            )

        master = db.scalar(
            select(Master).where(
                Master.user_id == invited_user.id
            )
        )

        if master is not None:
            if master.salon_id == salon.id:
                raise ValueError(
                    "Этот мастер уже состоит в вашем салоне."
                )

            if master.salon_id is not None:
                raise ValueError(
                    "Этот мастер уже состоит в другом салоне."
                )

        owned_salon = db.scalar(
            select(Salon.id)
            .where(
                Salon.owner_id == invited_user.id,
                Salon.is_active.is_(True),
            )
            .limit(1)
        )

        if owned_salon is not None:
            raise ValueError(
                "Пользователь является владельцем активного салона. "
                "Его нельзя присоединить к другому салону."
            )

        existing_invite = db.scalar(
            select(MasterInvite)
            .where(
                MasterInvite.salon_id == salon.id,
                MasterInvite.invited_user_id
                == invited_user.id,
                MasterInvite.status == "pending",
            )
            .order_by(
                MasterInvite.id.desc()
            )
            .limit(1)
        )

        if existing_invite is not None:
            invite_id = existing_invite.id
            salon_name = salon.name
            invited_name = (
                invited_user.first_name
                or str(invited_user.telegram_id)
            )

            db.rollback()

            await update.message.reply_text(
                "ℹ️ Такое приглашение уже ожидает ответа.\n\n"
                f"Приглашение: #{invite_id}\n"
                f"Мастер: {invited_name}",
                reply_markup=user_main_menu(
                    db,
                    owner,
                    update.effective_user.id,
                ),
            )
            clear_master_invite(
                context
            )
            return True

        invite = MasterInvite(
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
            or str(invited_user.telegram_id)
        )
        invited_telegram_id = (
            invited_user.telegram_id
        )

        db.commit()

        try:
            await context.bot.send_message(
                chat_id=invited_telegram_id,
                text=(
                    "🏢 Вас пригласили в салон GlowFlow.\n\n"
                    f"Салон: {salon_name}\n"
                    f"Приглашение: #{invite_id}\n\n"
                    "Выберите, принять или отклонить приглашение."
                ),
                reply_markup=invite_decision_menu(
                    invite_id
                ),
            )
        except Exception:
            # Запрос остаётся в БД, даже если Telegram
            # временно не смог доставить сообщение.
            pass

        await update.message.reply_text(
            "✅ Приглашение отправлено.\n\n"
            f"Приглашение: #{invite_id}\n"
            f"Мастер: {invited_name}\n"
            f"Салон: {salon_name}\n\n"
            "Мастер будет добавлен только после принятия.",
            reply_markup=user_main_menu(
                db,
                owner,
                update.effective_user.id,
            ),
        )

    except IntegrityError:
        db.rollback()

        await update.message.reply_text(
            "ℹ️ Такое приглашение уже ожидает ответа.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    except ValueError as error:
        db.rollback()

        await update.message.reply_text(
            f"❌ {error}",
            reply_markup=user_main_menu(
                db,
                owner if "owner" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось создать приглашение.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()
        clear_master_invite(
            context
        )

    return True


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
                "Пользователь не найден или отключён."
            )

        invite = db.scalar(
            select(MasterInvite)
            .options(
                joinedload(
                    MasterInvite.salon
                ),
                joinedload(
                    MasterInvite.invited_by
                ),
            )
            .where(
                MasterInvite.id == invite_id,
                MasterInvite.invited_user_id
                == invited_user.id,
            )
            .with_for_update()
        )

        if invite is None:
            raise ValueError(
                "Приглашение не найдено или адресовано другому пользователю."
            )

        if invite.status != "pending":
            raise ValueError(
                f"Приглашение уже обработано: {invite.status}."
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
                "Салон больше не активен."
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
                "Приглашение пока нельзя принять: "
                f"{reason}"
            )

        master = db.scalar(
            select(Master)
            .where(
                Master.user_id == invited_user.id
            )
            .with_for_update()
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
            db.flush()

        else:
            if master.salon_id == salon.id:
                invite.status = "accepted"
                invite.resolved_at = local_naive_now()
                db.add(invite)
                db.commit()

                await update.message.reply_text(
                    "ℹ️ Вы уже состоите в этом салоне.",
                    reply_markup=user_main_menu(
                        db,
                        invited_user,
                        update.effective_user.id,
                    ),
                )
                return

            if master.salon_id is not None:
                raise ValueError(
                    "Вы уже состоите в другом салоне."
                )

            master.salon_id = salon.id
            master.branch_id = None
            master.booking_enabled = False

        main_branch = db.scalar(
            select(Branch)
            .where(
                Branch.salon_id == salon.id
            )
            .order_by(
                Branch.id.asc()
            )
            .limit(1)
        )

        if main_branch is not None:
            master.branch_id = main_branch.id

        # Не ломаем роль owner. Обычный пользователь
        # становится мастером после собственного согласия.
        if invited_user.role == "client":
            invited_user.role = "master"

        now = local_naive_now()

        invite.status = "accepted"
        invite.resolved_at = now

        # Все остальные pending-приглашения этому
        # пользователю становятся неактуальными.
        db.execute(
            update(MasterInvite)
            .where(
                MasterInvite.invited_user_id
                == invited_user.id,
                MasterInvite.status == "pending",
                MasterInvite.id != invite.id,
            )
            .values(
                status="replaced",
                resolved_at=now,
            )
        )

        db.add(master)
        db.add(invited_user)
        db.add(invite)
        db.commit()

        salon_name = salon.name
        branch_name = (
            main_branch.name
            if main_branch is not None
            else "не назначен"
        )
        owner_telegram_id = (
            invite.invited_by.telegram_id
            if invite.invited_by is not None
            else None
        )

        await update.message.reply_text(
            "✅ Приглашение принято!\n\n"
            f"Салон: {salon_name}\n"
            f"Филиал: {branch_name}\n\n"
            "Приём новых записей пока выключен. "
            "Проверьте услуги и расписание, затем включите запись.",
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
                        "✅ Мастер принял приглашение.\n\n"
                        f"Салон: {salon_name}\n"
                        "Мастер: "
                        f"{invited_user.first_name or invited_user.telegram_id}"
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
            "❌ Не удалось принять приглашение.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def reject_master_invite(
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
            select(User).where(
                User.telegram_id
                == update.effective_user.id
            )
        )

        if invited_user is None:
            raise ValueError(
                "Пользователь не найден."
            )

        invite = db.scalar(
            select(MasterInvite)
            .options(
                joinedload(
                    MasterInvite.salon
                ),
                joinedload(
                    MasterInvite.invited_by
                ),
            )
            .where(
                MasterInvite.id == invite_id,
                MasterInvite.invited_user_id
                == invited_user.id,
            )
            .with_for_update()
        )

        if invite is None:
            raise ValueError(
                "Приглашение не найдено или адресовано другому пользователю."
            )

        if invite.status != "pending":
            raise ValueError(
                f"Приглашение уже обработано: {invite.status}."
            )

        invite.status = "rejected"
        invite.resolved_at = local_naive_now()
        db.add(invite)
        db.commit()

        salon_name = (
            invite.salon.name
            if invite.salon is not None
            else f"Салон #{invite.salon_id}"
        )

        await update.message.reply_text(
            "❌ Приглашение отклонено.\n\n"
            f"Салон: {salon_name}",
            reply_markup=user_main_menu(
                db,
                invited_user,
                update.effective_user.id,
            ),
        )

        if invite.invited_by is not None:
            try:
                await context.bot.send_message(
                    chat_id=invite.invited_by.telegram_id,
                    text=(
                        "❌ Мастер отклонил приглашение.\n\n"
                        f"Салон: {salon_name}\n"
                        "Пользователь: "
                        f"{invited_user.first_name or invited_user.telegram_id}"
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


async def master_invite_decision_router(
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
    reject_prefix = "❌ Отклонить приглашение #"

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

    if text_value.startswith(
        reject_prefix
    ):
        raw_id = text_value.removeprefix(
            reject_prefix
        ).strip()

        if raw_id.isdigit():
            await reject_master_invite(
                update,
                context,
                int(raw_id),
            )


master_invite_decision_handler = MessageHandler(
    filters.Regex(
        r"^(✅ Принять приглашение #[0-9]+|"
        r"❌ Отклонить приглашение #[0-9]+)$"
    ),
    master_invite_decision_router,
)
