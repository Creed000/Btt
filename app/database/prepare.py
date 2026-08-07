from importlib import import_module

from app.database.init_db import init_db
from app.database.schema_upgrade import (
    upgrade_database_schema,
)
from app.database.booking_reminder_upgrade import (
    upgrade_booking_reminder_delivery_flags,
)


def _run_optional_upgrade(
    module_name: str,
    function_name: str,
) -> None:
    """
    Позволяет prepare.py работать и на старой ветке,
    и после предыдущих SaaS-шагов.
    """
    try:
        module = import_module(
            module_name
        )
    except ImportError:
        return

    function = getattr(
        module,
        function_name,
        None,
    )

    if callable(function):
        function()


def prepare_database() -> None:
    # Сначала создаём отсутствующие таблицы.
    init_db()

    # Затем обновляем старую схему SaaS.
    upgrade_database_schema()

    # Upgrade пользовательских настроек из
    # предыдущих шагов, если файл уже установлен.
    _run_optional_upgrade(
        "app.database.user_settings_upgrade",
        "upgrade_user_notification_settings",
    )

    # RESTRICT для service_id из предыдущих шагов.
    _run_optional_upgrade(
        "app.database.booking_foreign_key_upgrade",
        "upgrade_booking_service_foreign_key",
    )

    # Новые раздельные reminder-флаги.
    upgrade_booking_reminder_delivery_flags()
