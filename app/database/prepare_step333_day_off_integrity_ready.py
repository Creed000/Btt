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
from app.database.salon_owner_upgrade import (
    upgrade_active_salon_owner_uniqueness,
)
from app.database.service_unique_upgrade import (
    upgrade_service_title_uniqueness,
)
from app.database.category_unique_upgrade import (
    upgrade_category_name_uniqueness,
)
from app.database.city_unique_upgrade import (
    upgrade_city_name_uniqueness,
)
from app.database.branch_unique_upgrade import (
    upgrade_branch_name_uniqueness,
)
from app.database.master_booking_default_upgrade import (
    upgrade_master_booking_default,
)
from app.database.master_schedule_integrity_upgrade import (
    upgrade_master_schedule_integrity,
)
from app.database.master_day_off_integrity_upgrade import (
    upgrade_master_day_off_integrity,
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

    # 8. Один активный салон на владельца.
    upgrade_active_salon_owner_uniqueness()

    # 9. Уникальное название услуги внутри одного мастера.
    upgrade_service_title_uniqueness()

    # 10. Уникальное нормализованное имя категории.
    upgrade_category_name_uniqueness()

    # 11. Уникальное нормализованное имя города.
    upgrade_city_name_uniqueness()

    # 12. Уникальное имя филиала внутри салона.
    upgrade_branch_name_uniqueness()

    # 13. Безопасный DB-default для booking_enabled.
    upgrade_master_booking_default()

    # 14. Одна строка расписания на master + weekday.
    upgrade_master_schedule_integrity()

    # 15. Одна выходная дата на master + date.
    upgrade_master_day_off_integrity()
