import logging

from telegram import Update

from app.bot.bot import application
from app.bot.run import prepare_database


logger = logging.getLogger(__name__)


if __name__ == "__main__":
    prepare_database()

    logger.info(
        "Запуск Telegram-бота через run_bot.py"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )
