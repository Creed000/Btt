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
from app.database.master_time_block_integrity_upgrade import (
    upgrade_master_time_block_integrity,
)
from app.database.booking_status_integrity_upgrade import (
    upgrade_booking_status_integrity,
)
from app.database.booking_core_integrity_upgrade import (
    upgrade_booking_core_integrity,
)
from app.database.booking_active_slot_integrity_upgrade import (
    upgrade_booking_active_slot_uniqueness,
)
from app.database.booking_duration_snapshot_upgrade import (
    upgrade_booking_duration_snapshot,
)
from app.database.booking_price_snapshot_upgrade import (
    upgrade_booking_price_snapshot,
)
from app.database.service_booking_business_bounds_upgrade import (
    upgrade_service_booking_business_bounds,
)
from app.database.service_core_integrity_upgrade import (
    upgrade_service_core_integrity,
)
from app.database.category_core_integrity_upgrade import (
    upgrade_category_core_integrity,
)
from app.database.core_delete_restrictions_upgrade import (
    upgrade_core_delete_restrictions,
)
from app.database.salon_child_delete_restrictions_upgrade import (
    upgrade_salon_child_delete_restrictions,
)
from app.database.user_history_delete_restrictions_upgrade import (
    upgrade_user_history_delete_restrictions,
)
from app.database.booking_overlap_integrity_upgrade import (
    upgrade_booking_overlap_exclusion,
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

    # 16. Целостность блокировок времени мастера.
    upgrade_master_time_block_integrity()

    # 17. Допустимые статусы Booking на уровне БД.
    upgrade_booking_status_integrity()

    # 18. Обязательные core-поля Booking в старой БД.
    upgrade_booking_core_integrity()


    # 19. Снимок длительности услуги внутри Booking.
    upgrade_booking_duration_snapshot()

    # 20. Снимок цены услуги внутри Booking.
    upgrade_booking_price_snapshot()

    # 21. Границы длительности и цены Service/Booking.
    upgrade_service_booking_business_bounds()

    # 22. Обязательные поля и FK Service.
    upgrade_service_core_integrity()

    # 23. Обязательное непустое имя Category.
    upgrade_category_core_integrity()


    # 24. Запрет каскадного удаления основной SaaS-истории.
    upgrade_core_delete_restrictions()


    # 25. Защита дочерних данных Salon от CASCADE.
    upgrade_salon_child_delete_restrictions()


    # 26. Защита клиентской/audit-истории User.
    upgrade_user_history_delete_restrictions()

    # 27. Уникальные активные слоты мастера и клиента.
    upgrade_booking_active_slot_uniqueness()


    # 28. DB-защита от пересекающихся активных интервалов.
    upgrade_booking_overlap_exclusion()
