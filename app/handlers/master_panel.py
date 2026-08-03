from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.user import User


async def become_master(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None or update.effective_user is None:
        return

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Сначала отправьте /start.",
                reply_markup=main_menu(),
            )
            return

        if not user.is_active:
            await update.message.reply_text(
                "❌ Ваш аккаунт временно отключён.",
                reply_markup=main_menu(),
            )
            return

        existing_master = db.scalar(
            select(Master).where(
                Master.user_id == user.id
            )
        )

        if existing_master is not None:
            await update.message.reply_text(
                "💼 Кабинет мастера\n\n"
                f"ID мастера: {existing_master.id}\n"
                f"Рейтинг: {existing_master.rating:.1f}\n"
                f"Приём записей: "
                f"{'включён' if existing_master.booking_enabled else 'выключен'}\n"
                f"Проверка профиля: "
                f"{'пройдена' if existing_master.is_verified else 'ожидается'}",
                reply_markup=main_menu(),
            )
            return

        master = Master(
            user_id=user.id,
            description="Новый мастер BTT",
            slug=f"master-{user.telegram_id}",
            rating=5.0,
            booking_enabled=True,
            is_verified=False,
        )

        user.role = "master"

        db.add(master)
        db.add(user)
        db.commit()
        db.refresh(master)

        await update.message.reply_text(
            "🎉 Профиль мастера создан!\n\n"
            f"ID мастера: {master.id}\n"
            "Статус проверки: ожидается\n"
            "Приём записей: включён\n\n"
            "Следующим этапом добавим услуги, цены и расписание.",
            reply_markup=main_menu(),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось создать профиль мастера. Попробуйте позже.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()
