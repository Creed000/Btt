import logging

from sqlalchemy import select, text
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.keyboards.main import main_menu
from app.models.user import User
from app.services.access_control import can_manage_platform
from app.services.timezone import APP_TIMEZONE, local_naive_now


logger = logging.getLogger(__name__)


def get_job_status(
    context: ContextTypes.DEFAULT_TYPE,
    job_name: str,
) -> str:
    job_queue = context.application.job_queue

    if job_queue is None:
        return "❌ JobQueue недоступна"

    jobs = job_queue.get_jobs_by_name(
        job_name
    )

    if not jobs:
        return "❌ задача не найдена"

    return "✅ активна"


async def health_check(
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

        if not can_manage_platform(user):
            role = (
                user.role
                if user is not None
                else None
            )

            await update.message.reply_text(
                "⛔ Команда /health доступна только "
                "администратору SaaS-платформы.",
                reply_markup=main_menu(
                    role=role,
                    telegram_id=update.effective_user.id,
                ),
            )
            return

        database_status = "❌ недоступна"

        try:
            db.execute(
                text("SELECT 1")
            )
            database_status = "✅ доступна"
        except Exception:
            logger.exception(
                "Ошибка проверки подключения к базе данных"
            )

        job_queue_status = (
            "✅ запущена"
            if context.application.job_queue is not None
            else "❌ недоступна"
        )

        reminder_job_status = get_job_status(
            context,
            "booking_reminders",
        )

        subscription_job_status = get_job_status(
            context,
            "subscription_maintenance",
        )

        now = local_naive_now()

        await update.message.reply_text(
            "🩺 Состояние системы\n\n"
            "Telegram-бот: ✅ работает\n"
            f"PostgreSQL: {database_status}\n"
            f"JobQueue: {job_queue_status}\n"
            f"Напоминания: {reminder_job_status}\n"
            f"Проверка подписок: {subscription_job_status}\n"
            f"Часовой пояс: {APP_TIMEZONE}\n"
            f"Локальное время: "
            f"{now.strftime('%d.%m.%Y %H:%M:%S')}"
        )

    except Exception:
        logger.exception(
            "Ошибка выполнения команды /health"
        )

        await update.message.reply_text(
            "❌ Не удалось выполнить проверку состояния системы.",
            reply_markup=main_menu(
                telegram_id=update.effective_user.id,
            ),
        )

    finally:
        db.close()


health_handler = CommandHandler(
    "health",
    health_check,
)
