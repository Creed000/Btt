from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.booking import Booking
from app.models.master import Master
from app.models.salon import Salon
from app.models.user import User
from app.services.timezone import local_naive_now


def user_main_menu(db, user: User | None, telegram_id: int):
    if user is None:
        return main_menu(telegram_id=telegram_id)

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
            .where(Master.user_id == user.id)
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


def has_future_active_bookings(db, master_id: int) -> bool:
    now = local_naive_now()

    booking_id = db.scalar(
        select(Booking.id)
        .where(
            Booking.master_id == master_id,
            Booking.status.in_(("new", "confirmed")),
            or_(
                Booking.booking_date > now.date(),
                (
                    (Booking.booking_date == now.date())
                    & (Booking.booking_time >= now.time())
                ),
            ),
        )
        .limit(1)
    )

    return booking_id is not None


async def remove_master_from_salon(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    master_id: int,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        owner = db.scalar(
            select(User)
            .where(User.telegram_id == update.effective_user.id)
            .with_for_update()
        )

        if owner is None or not owner.is_active:
            raise ValueError("Пользователь не найден или отключён.")

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
            raise ValueError("Активный салон не найден.")

        master = db.scalar(
            select(Master)
            .options(joinedload(Master.user))
            .where(
                Master.id == master_id,
                Master.salon_id == salon.id,
            )
            .with_for_update()
        )

        if master is None:
            raise ValueError(
                "Мастер не найден или уже не состоит в вашем салоне."
            )

        if master.user_id == owner.id:
            raise ValueError(
                "Нельзя убрать из салона самого владельца."
            )

        if has_future_active_bookings(db, master.id):
            raise ValueError(
                "У мастера есть будущие активные записи. "
                "Сначала завершите или отмените их."
            )

        master_name = (
            master.user.first_name
            if master.user and master.user.first_name
            else f"Мастер #{master.id}"
        )
        master_telegram_id = (
            master.user.telegram_id if master.user else None
        )
        salon_name = salon.name

        # Профиль и история остаются. Убираем только связь с салоном.
        master.salon_id = None
        master.branch_id = None
        master.booking_enabled = False

        db.add(master)
        db.commit()

        await update.message.reply_text(
            "✅ Мастер убран из салона.\n\n"
            f"Мастер: {master_name}\n"
            f"Салон: {salon_name}\n\n"
            "Профиль, услуги, расписание и история записей сохранены.\n"
            "Приём новых записей выключен.",
            reply_markup=user_main_menu(
                db,
                owner,
                update.effective_user.id,
            ),
        )

        if master_telegram_id is not None:
            try:
                await context.bot.send_message(
                    chat_id=master_telegram_id,
                    text=(
                        "ℹ️ Вы больше не привязаны к салону "
                        f"«{salon_name}».\n\n"
                        "Ваш профиль и история сохранены. "
                        "Приём новых записей временно выключен."
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
                owner if "owner" in locals() else None,
                update.effective_user.id,
            ),
        )

    except Exception:
        db.rollback()
        await update.message.reply_text(
            "❌ Не удалось убрать мастера из салона.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


async def master_removal_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.message.text is None:
        return

    prefix = "🚪 Убрать мастера #"
    text_value = update.message.text.strip()

    if not text_value.startswith(prefix):
        return

    raw_id = text_value.removeprefix(prefix).strip()
    if not raw_id.isdigit():
        return

    await remove_master_from_salon(
        update,
        context,
        int(raw_id),
    )


master_removal_handler = MessageHandler(
    filters.Regex(r"^🚪 Убрать мастера #[0-9]+$"),
    master_removal_router,
)
