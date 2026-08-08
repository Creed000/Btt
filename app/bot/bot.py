import logging
import traceback

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ContextTypes,
)

from app.config.settings import settings
from app.handlers.booking import booking_handler
from app.handlers.branch_manager import branch_delete_handler
from app.handlers.master_removal import master_removal_handler
from app.handlers.master_invite import master_invite_response_handler
from app.handlers.admin_subscriptions import admin_subscription_requests_handler
from app.handlers.health import health_handler
from app.handlers.menu import menu_handler
from app.handlers.profile import profile_handler
from app.handlers.search import search_handler
from app.handlers.settings import settings_handler
from app.handlers.start import start_handler
from app.handlers.telegram_id import telegram_id_handler
from app.services.booking_reminders import (
    process_booking_reminders,
)
from app.services.subscription_maintenance import (
    maintain_salon_subscriptions,
)
from app.services.master_invite_maintenance import (
    expire_stale_master_invites,
)


logger = logging.getLogger(__name__)


async def booking_reminders_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Отдельная защищённая задача напоминаний.
    Ошибка здесь не должна остановить остальные job.
    """
    try:
        await process_booking_reminders(
            context.application,
        )
    except Exception:
        logger.exception(
            "Ошибка фоновой задачи booking_reminders."
        )


async def subscription_maintenance_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Проверяет истёкшие trial/подписки и выключает
    приём новых записей у мастеров таких салонов.
    """
    try:
        maintain_salon_subscriptions()
    except Exception:
        logger.exception(
            "Ошибка фоновой задачи "
            "subscription_maintenance."
        )



async def master_invite_maintenance_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    try:
        expire_stale_master_invites()
    except Exception:
        logger.exception(
            "Ошибка фоновой задачи "
            "master_invite_maintenance."
        )

def _ensure_repeating_job(
    application: Application,
    *,
    name: str,
    callback,
    interval: int,
    first: int,
) -> bool:
    job_queue = application.job_queue

    if job_queue is None:
        return False

    existing_jobs = (
        job_queue.get_jobs_by_name(
            name
        )
    )

    if existing_jobs:
        logger.info(
            "Фоновая задача %s уже зарегистрирована.",
            name,
        )
        return True

    job_queue.run_repeating(
        callback=callback,
        interval=interval,
        first=first,
        name=name,
    )

    logger.info(
        "Фоновая задача %s зарегистрирована.",
        name,
    )
    return True


async def post_init(
    application: Application,
) -> None:
    """
    Telegram-команды + независимый запуск
    всех фоновых задач.
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
            "JobQueue недоступен. Установите "
            "python-telegram-bot[job-queue]."
        )
        return

    # ВАЖНО: никаких ранних return между задачами.
    # Если одна уже существует, вторая всё равно
    # будет проверена и при необходимости создана.
    _ensure_repeating_job(
        application,
        name="booking_reminders",
        callback=booking_reminders_job,
        interval=300,
        first=30,
    )

    _ensure_repeating_job(
        application,
        name="subscription_maintenance",
        callback=subscription_maintenance_job,
        interval=3600,
        first=60,
    )

    _ensure_repeating_job(
        application,
        name="master_invite_maintenance",
        callback=master_invite_maintenance_job,
        interval=3600,
        first=90,
    )

    logger.info(
        "Фоновые задачи GlowFlow активированы: "
        "напоминания каждые 5 минут, "
        "подписки и приглашения каждый час."
    )


async def global_error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
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
            "Не удалось отправить пользователю "
            "сообщение об ошибке."
        )


application = (
    Application.builder()
    .token(settings.BOT_TOKEN)
    .post_init(post_init)
    .build()
)


# Команды.
application.add_handler(start_handler)
application.add_handler(telegram_id_handler)
application.add_handler(health_handler)

# Специальные админ-кнопки должны обрабатываться
# раньше общего menu_handler.
application.add_handler(admin_subscription_requests_handler)
application.add_handler(branch_delete_handler)
application.add_handler(master_removal_handler)
application.add_handler(master_invite_response_handler)

# Основные обработчики.
application.add_handler(menu_handler)
application.add_handler(booking_handler)
application.add_handler(profile_handler)
application.add_handler(search_handler)
application.add_handler(settings_handler)

# Глобальная страховка.
application.add_error_handler(
    global_error_handler
)
