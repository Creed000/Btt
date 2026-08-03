import logging

from telegram import Update

from app.bot.bot import application
from app.database.init_db import init_db
from app.database.schema_upgrade import upgrade_database_schema


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


def prepare_database() -> None:
    logger.info("Проверка таблиц базы данных")
    init_db()

    logger.info("Проверка и обновление SaaS-схемы")
    upgrade_database_schema()

    logger.info("База данных готова")


if __name__ == "__main__":
    prepare_database()

    logger.info("Запуск Telegram-бота")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )
