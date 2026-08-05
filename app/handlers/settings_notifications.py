from sqlalchemy import select
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.database.session import SessionLocal
from app.handlers.settings_panel import settings_menu
from app.models.user import User


def notifications_menu(
    enabled: bool,
) -> ReplyKeyboardMarkup:
    action_button = (
        "🔕 Выключить уведомления"
        if enabled
        else "🔔 Включить уведомления"
    )

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(action_button)],
            [KeyboardButton("⬅️ Назад к настройкам")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Настройка уведомлений",
    )


async def open_notification_settings(
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
                "❌ Пользователь не найден. Отправьте /start."
            )
            return

        status_text = (
            "✅ включены"
            if user.notifications_enabled
            else "❌ выключены"
        )

        await update.message.reply_text(
            "🔔 Настройки уведомлений\n\n"
            f"Текущий статус: {status_text}\n\n"
            "Эта настройка влияет на напоминания "
            "и сообщения об изменении статуса записи.",
            reply_markup=notifications_menu(
                user.notifications_enabled
            ),
        )

    except Exception:
        await update.message.reply_text(
            "❌ Не удалось открыть настройки уведомлений.",
            reply_markup=settings_menu(),
        )

    finally:
        db.close()


async def change_user_notifications(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    if (
        update.message is None
        or update.message.text is None
        or update.effective_user is None
    ):
        return False

    text = update.message.text.strip()

    if text not in {
        "🔕 Выключить уведомления",
        "🔔 Включить уведомления",
    }:
        return False

    enabled = (
        text == "🔔 Включить уведомления"
    )

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_id == update.effective_user.id
            )
        )

        if user is None:
            await update.message.reply_text(
                "❌ Пользователь не найден. Отправьте /start."
            )
            return True

        user.notifications_enabled = enabled
        db.commit()

        status_text = (
            "✅ Уведомления включены."
            if enabled
            else "🔕 Уведомления выключены."
        )

        await update.message.reply_text(
            status_text,
            reply_markup=settings_menu(),
        )

        return True

    except Exception:
        db.rollback()

        await update.message.reply_text(
            "❌ Не удалось изменить настройку уведомлений.",
            reply_markup=settings_menu(),
        )

        return True

    finally:
        db.close()
