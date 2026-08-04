import asyncio
import logging
import traceback

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ContextTypes,
)

from app.config.settings import settings
from app.handlers.health import health_handler
from app.handlers.menu import menu_handler
from app.handlers.start import start_handler
from app.handlers.telegram_id import telegram_id_handler
from app.services.booking_reminders import (
    process_booking_reminders,
)
from app.services.subscription_maintenance import (
    process_expired_salon_access,
)


logger = logging.getLogger(__name__)


async def booking_reminders_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Проверяет ближайшие записи и отправляет напоминания.
    """
    await process_booking_reminders(
        context.application,
    )


async def subscription_maintenance_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Проверяет пробные периоды и подписки салонов.

    Синхронная работа с SQLAlchemy выполняется в отдельном потоке,
    чтобы не блокировать обработку сообщений Telegram.
    """
    try:
        result = await asyncio.to_thread(
            process_expired_salon_access
        )

        logger.info(
            "Проверка подписок завершена: "
            "салонов проверено=%s, "
            "просрочено=%s, "
            "мастеров отключено=%s",
            result["checked_salons"],
            result["expired_salons"],
            result["disabled_masters"],
        )

    except Exception:
        logger.exception(
            "Ошибка фоновой проверки подписок салонов"
        )


async def post_init(
    application: Application,
) -> None:
    """
    Настраивает команды и фоновые задачи после запуска приложения.
    """
    await application.bot.set_my_commands(
        [
            BotCommand(
                command="start",
                description="Открыть главное меню",
            ),
            BotCommand(
                command="id",
                description="Показать мой Telegram ID",
            ),
            BotCommand(
                command="health",
                description="Проверить состояние системы",
            ),
        ]
    )

    logger.info(
        "Команды Telegram успешно зарегистрированы."
    )

    if application.job_queue is None:
        logger.error(
            "JobQueue недоступен. "
            "Проверьте установку python-telegram-bot[job-queue]."
        )
        return

    if not application.job_queue.get_jobs_by_name(
        "booking_reminders"
    ):
        application.job_queue.run_repeating(
            callback=booking_reminders_job,
            interval=300,
            first=30,
            name="booking_reminders",
        )

        logger.info(
            "Напоминания запущены: проверка каждые 5 минут."
        )

    if not application.job_queue.get_jobs_by_name(
        "subscription_maintenance"
    ):
        application.job_queue.run_repeating(
            callback=subscription_maintenance_job,
            interval=3600,
            first=60,
            name="subscription_maintenance",
        )

        logger.info(
            "Проверка подписок запущена: каждый час."
        )


async def global_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Логирует любую необработанную ошибку Telegram-бота.
    """
    error = context.error

    if error is None:
        error_text = "Неизвестная ошибка"
    else:
        error_text = "".join(
            traceback.format_exception(
                type(error),
                error,
                error.__traceback__,
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


# Команды Telegram.
application.add_handler(start_handler)
application.add_handler(telegram_id_handler)
application.add_handler(health_handler)

# Единый маршрутизатор всех текстовых кнопок и диалогов.
application.add_handler(menu_handler)

# Глобальный обработчик ошибок.
application.add_error_handler(
    global_error_handler
)
