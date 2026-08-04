import logging

from telegram.ext import (
    Application,
    ContextTypes,
)

from app.config.settings import settings
from app.handlers.booking import booking_handler
from app.handlers.menu import menu_handler
from app.handlers.profile import profile_handler
from app.handlers.search import search_handler
from app.handlers.settings import settings_handler
from app.handlers.start import start_handler
from app.services.booking_reminders import (
    process_booking_reminders,
)


logger = logging.getLogger(__name__)


async def booking_reminders_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Периодическая задача проверки напоминаний.
    """
    await process_booking_reminders(
        context.application,
    )


async def post_init(
    application: Application,
) -> None:
    """
    Запускается после инициализации Telegram Application.
    """
    if application.job_queue is None:
        logger.error(
            "JobQueue недоступен. "
            "Проверьте установку APScheduler."
        )
        return

    # Защита от повторного добавления задачи.
    existing_jobs = application.job_queue.get_jobs_by_name(
        "booking_reminders"
    )

    if existing_jobs:
        logger.info(
            "Задача напоминаний уже зарегистрирована."
        )
        return

    application.job_queue.run_repeating(
        callback=booking_reminders_job,
        interval=300,
        first=30,
        name="booking_reminders",
    )

    logger.info(
        "Автоматические напоминания запущены: "
        "проверка каждые 5 минут."
    )


application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .post_init(post_init)
    .build()
)


# Регистрация обработчиков.
application.add_handler(start_handler)
application.add_handler(menu_handler)
application.add_handler(booking_handler)
application.add_handler(profile_handler)
application.add_handler(search_handler)
application.add_handler(settings_handler)
