import logging

from app.database.booking_foreign_key_upgrade import (
    upgrade_booking_service_foreign_key,
)
from app.database.init_db import init_db
from app.database.schema_upgrade import upgrade_database_schema
from app.database.user_settings_upgrade import (
    upgrade_user_notification_settings,
)


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
        "Обновление настроек уведомлений пользователей"
    )
    upgrade_user_notification_settings()

    logger.info(
        "Обновление внешнего ключа bookings.service_id"
    )
    upgrade_booking_service_foreign_key()

    logger.info(
        "База данных полностью готова"
    )
