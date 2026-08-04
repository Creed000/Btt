import logging
import traceback

from telegram import Update
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
from app.handlers.telegram_id import telegram_id_handler
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
            "Проверьте установку python-telegram-bot[job-queue]."
        )
        return

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


async def global_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Логирует любую необработанную ошибку Telegram-бота.
    """
    error_text = "".join(
        traceback.format_exception(
            type(context.error),
            context.error,
            context.error.__traceback__,
        )
    )

    logger.error(
        "Необработанная ошибка Telegram-бота:\n%s",
        error_text,
    )

    if not isinstance(update, Update):
        return

    message = update.effective_message

    if message is None:
        return

    try:
        await message.reply_text(
            "❌ Произошла непредвиденная ошибка.\n\n"
            "Попробуйте ещё раз или отправьте /start."
        )
    except Exception:
        logger.exception(
            "Не удалось отправить пользователю сообщение об ошибке."
        )


application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .post_init(post_init)
    .build()
)


# Регистрация обработчиков команд.
application.add_handler(start_handler)
application.add_handler(telegram_id_handler)

# Регистрация остальных обработчиков.
application.add_handler(menu_handler)
application.add_handler(booking_handler)
application.add_handler(profile_handler)
application.add_handler(search_handler)
application.add_handler(settings_handler)

# Глобальный обработчик непредвиденных ошибок.
application.add_error_handler(
    global_error_handler
)
