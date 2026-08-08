import logging

from telegram import Update

from app.bot.bot import application
from app.database.prepare import prepare_database
from app.services.timezone import APP_TIMEZONE


logging.basicConfig(
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    ),
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def run() -> None:
    """
    Единственная точка безопасного запуска GlowFlow.

    Порядок критичен:
    1. Сначала таблицы и все идемпотентные upgrades.
    2. Только после успешной подготовки БД запускается Telegram.
    3. post_init из app.bot.bot зарегистрирует фоновые jobs.
    """
    logger.info(
        "GlowFlow starting. APP_TIMEZONE=%s",
        APP_TIMEZONE,
    )

    try:
        logger.info(
            "Подготовка базы данных..."
        )

        prepare_database()

        logger.info(
            "База данных полностью подготовлена."
        )

    except Exception:
        logger.exception(
            "Критическая ошибка подготовки БД. "
            "Telegram polling НЕ будет запущен."
        )
        raise

    logger.info(
        "Запуск Telegram polling..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,

        # Не удаляем сообщения, которые пришли во время
        # короткого рестарта Railway.
        drop_pending_updates=False,

        # Railway/Telegram могут временно быть недоступны
        # во время старта — повторяем bootstrap.
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    run()
