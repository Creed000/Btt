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
from app.database.master_invite_upgrade import (
    upgrade_master_invites,
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
    # Сначала создаём отсутствующие таблицы.
    init_db()

    upgrade_database_schema()

    _run_optional_upgrade(
        "app.database.user_settings_upgrade",
        "upgrade_user_notification_settings",
    )

    _run_optional_upgrade(
        "app.database.booking_foreign_key_upgrade",
        "upgrade_booking_service_foreign_key",
    )

    upgrade_booking_reminder_delivery_flags()
    upgrade_subscription_plan_requests()
    upgrade_master_invites()
