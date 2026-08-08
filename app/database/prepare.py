from importlib import import_module

from app.database.init_db import init_db
from app.database.schema_upgrade import (
    upgrade_database_schema,
)
from app.database.booking_reminder_upgrade import (
    upgrade_booking_reminder_delivery_flags,
)
from app.database.subscription_plan_request_upgrade import (
    upgrade_subscription_plan_requests,
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
    # 1. Сначала создаём все отсутствующие таблицы,
    # включая subscription_plan_requests.
    init_db()

    # 2. Затем обновляем старую схему SaaS.
    upgrade_database_schema()

    # 3. Настройки пользователей.
    _run_optional_upgrade(
        "app.database.user_settings_upgrade",
        "upgrade_user_notification_settings",
    )

    # 4. Историческая защита service_id.
    _run_optional_upgrade(
        "app.database.booking_foreign_key_upgrade",
        "upgrade_booking_service_foreign_key",
    )

    # 5. Раздельные флаги напоминаний.
    upgrade_booking_reminder_delivery_flags()

    # 6. Гарантия одного pending-запроса
    # тарифа на один салон.
    upgrade_subscription_plan_requests()
