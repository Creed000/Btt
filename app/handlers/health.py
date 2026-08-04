import logging

from sqlalchemy import text
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from app.database.session import SessionLocal
from app.services.timezone import APP_TIMEZONE, local_naive_now


logger = logging.getLogger(__name__)


async def health_check(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if update.message is None:
        return

    database_status = "❌ недоступна"

    db = SessionLocal()

    try:
        db.execute(
            text("SELECT 1")
        )
        database_status = "✅ доступна"
    except Exception:
        logger.exception(
            "Ошибка проверки подключения к базе данных"
        )
    finally:
        db.close()

    job_queue_status = (
        "✅ запущена"
        if context.application.job_queue is not None
        else "❌ недоступна"
    )

    reminder_job_status = "❌ не найдена"

    if context.application.job_queue is not None:
        jobs = context.application.job_queue.get_jobs_by_name(
            "booking_reminders"
        )

        if jobs:
            reminder_job_status = "✅ активна"

    now = local_naive_now()

    await update.message.reply_text(
        "🩺 Состояние системы\n\n"
        f"Telegram-бот: ✅ работает\n"
        f"PostgreSQL: {database_status}\n"
        f"JobQueue: {job_queue_status}\n"
        f"Напоминания: {reminder_job_status}\n"
        f"Часовой пояс: {APP_TIMEZONE}\n"
        f"Локальное время: {now.strftime('%d.%m.%Y %H:%M:%S')}"
    )


health_handler = CommandHandler(
    "health",
    health_check,
)
