from sqlalchemy import func, select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.master import Master
from app.models.service import Service
from app.models.user import User


def master_panel_menu(master: Master) -> ReplyKeyboardMarkup:
    booking_button = (
        "⛔ Выключить запись"
        if master.booking_enabled
        else "✅ Включить запись"
    )

    keyboard = [
        [KeyboardButton("➕ Добавить услугу")],
        [KeyboardButton("📋 Мои услуги")],
        [KeyboardButton(booking_button)],
        [KeyboardButton("⬅️ Назад")],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Кабинет мастера",
    )


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

        master = db.scalar(
            select(Master).where(
                Master.user_id == user.id
            )
        )

        if master is None:
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
                "🎉 Профиль мастера создан!",
                reply_markup=master_panel_menu(master),
            )
            return

        services_count = db.scalar(
            select(func.count(Service.id)).where(
                Service.master_id == master.id
            )
        )

        await update.message.reply_text(
            "💼 Кабинет мастера\n\n"
            f"🆔 ID мастера: {master.id}\n"
            f"⭐ Рейтинг: {master.rating:.1f}\n"
            f"📅 Приём записей: "
            f"{'включён' if master.booking_enabled else 'выключен'}\n"
            f"✅ Проверка профиля: "
            f"{'пройдена' if master.is_verified else 'ожидается'}\n"
            f"💼 Услуг добавлено: {services_count or 0}",
            reply_markup=master_panel_menu(master),
        )

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось открыть кабинет мастера. Попробуйте позже.",
            reply_markup=main_menu(),
        )

    finally:
        db.close()
