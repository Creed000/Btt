import logging

from app.database.booking_foreign_key_upgrade import (
    upgrade_booking_service_foreign_key,
)
from app.database.init_db import init_db
from app.database.schema_upgrade import upgrade_database_schema


logger = logging.getLogger(__name__)


def prepare_database() -> None:
    """
    Полная подготовка базы данных перед запуском бота.
    """
    logger.info(
        "Проверка и создание таблиц базы данных"
    )
    init_db()

    logger.info(
        "Обновление SaaS-схемы базы данных"
    )
    upgrade_database_schema()

    logger.info(
        "Обновление внешнего ключа bookings.service_id"
    )
    upgrade_booking_service_foreign_key()

    logger.info(
        "База данных полностью готова"
    )
