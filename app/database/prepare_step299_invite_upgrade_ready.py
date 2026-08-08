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
from app.database.master_salon_invite_upgrade import (
    upgrade_master_salon_invites,
)


def _run_optional_upgrade(
    module_name: str,
    function_name: str,
) -> None:
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
    # 1. Создаём все отсутствующие таблицы.
    init_db()

    # 2. Обновляем старую схему.
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

    # 6. Один pending-запрос тарифа на салон.
    upgrade_subscription_plan_requests()

    # 7. Одно pending-приглашение мастера
    # для пары салон + пользователь.
    upgrade_master_salon_invites()
