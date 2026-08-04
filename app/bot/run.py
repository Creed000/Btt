import logging

from telegram import Update

from app.bot.bot import application
from app.database.prepare import prepare_database
from app.services.timezone import APP_TIMEZONE


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info(
        "Часовой пояс приложения: %s",
        APP_TIMEZONE,
    )

    prepare_database()

    logger.info(
        "Запуск Telegram-бота"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )
