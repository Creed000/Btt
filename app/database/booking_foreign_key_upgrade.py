import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


BOOKING_FOREIGN_KEYS = {
    "client_id": {
        "target_table": "users",
        "target_column": "id",
        "delete_rule": "CASCADE",
        "constraint_name": "fk_bookings_client_id",
    },
    "master_id": {
        "target_table": "masters",
        "target_column": "id",
        "delete_rule": "CASCADE",
        "constraint_name": "fk_bookings_master_id",
    },
    "service_id": {
        "target_table": "services",
        "target_column": "id",
        "delete_rule": "RESTRICT",
        "constraint_name": "fk_bookings_service_id",
    },
}


def _find_orphan_ids(
    connection,
    column_name: str,
    target_table: str,
) -> list[int]:
    rows = connection.execute(
        text(
            f"""
            SELECT b.id
            FROM bookings AS b
            LEFT JOIN {target_table} AS target
              ON target.id = b.{column_name}
            WHERE b.{column_name} IS NOT NULL
              AND target.id IS NULL
            ORDER BY b.id
            LIMIT 50
            """
        )
    ).scalars().all()

    return list(rows)


def _current_foreign_keys(
    connection,
    column_name: str,
) -> list[dict]:
    return list(
        connection.execute(
            text(
                """
                SELECT
                    tc.constraint_name,
                    ccu.table_name AS target_table,
                    ccu.column_name AS target_column,
                    rc.delete_rule
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.constraint_schema = kcu.constraint_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.constraint_schema = ccu.constraint_schema
                JOIN information_schema.referential_constraints AS rc
                  ON tc.constraint_name = rc.constraint_name
                 AND tc.constraint_schema = rc.constraint_schema
                WHERE tc.table_schema = current_schema()
                  AND tc.table_name = 'bookings'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = :column_name
                """
            ),
            {
                "column_name": column_name,
            },
        ).mappings()
    )


def _foreign_key_is_correct(
    foreign_keys: list[dict],
    target_table: str,
    target_column: str,
    delete_rule: str,
) -> bool:
    if len(foreign_keys) != 1:
        return False

    foreign_key = foreign_keys[0]

    actual_delete_rule = (
        foreign_key["delete_rule"] or ""
    ).upper()

    if delete_rule == "RESTRICT":
        delete_rule_ok = actual_delete_rule in {
            "RESTRICT",
            "NO ACTION",
        }
    else:
        delete_rule_ok = (
            actual_delete_rule == delete_rule
        )

    return (
        foreign_key["target_table"] == target_table
        and foreign_key["target_column"] == target_column
        and delete_rule_ok
    )


def _drop_foreign_keys(
    connection,
    foreign_keys: list[dict],
) -> None:
    for foreign_key in foreign_keys:
        constraint_name = foreign_key[
            "constraint_name"
        ]

        safe_name = constraint_name.replace(
            '"',
            '""',
        )

        connection.execute(
            text(
                f'ALTER TABLE bookings '
                f'DROP CONSTRAINT IF EXISTS "{safe_name}"'
            )
        )


def upgrade_booking_service_foreign_key() -> None:
    """
    Историческое имя функции сохранено для совместимости.

    Теперь upgrade защищает все основные внешние ключи Booking:
    client_id -> users.id ON DELETE CASCADE
    master_id -> masters.id ON DELETE CASCADE
    service_id -> services.id ON DELETE RESTRICT

    Перед созданием FK проверяет старые данные на сиротские ссылки.
    """
    if engine.dialect.name != "postgresql":
        logger.info(
            "Booking FK upgrade пропущен: "
            "используется не PostgreSQL."
        )
        return

    inspector = inspect(engine)
    table_names = set(
        inspector.get_table_names()
    )

    required_tables = {
        "bookings",
        "users",
        "masters",
        "services",
    }

    missing_tables = sorted(
        required_tables - table_names
    )

    if missing_tables:
        logger.info(
            "Booking FK upgrade пропущен: "
            "ещё отсутствуют таблицы %s.",
            ", ".join(missing_tables),
        )
        return

    booking_columns = {
        column["name"]
        for column in inspector.get_columns(
            "bookings"
        )
    }

    missing_columns = [
        column_name
        for column_name in BOOKING_FOREIGN_KEYS
        if column_name not in booking_columns
    ]

    if missing_columns:
        raise RuntimeError(
            "В bookings отсутствуют обязательные FK-поля: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        # Сначала проверяем данные. Ничего автоматически
        # не удаляем и не переназначаем.
        orphan_messages = []

        for (
            column_name,
            config,
        ) in BOOKING_FOREIGN_KEYS.items():
            orphan_ids = _find_orphan_ids(
                connection,
                column_name,
                config["target_table"],
            )

            if orphan_ids:
                orphan_messages.append(
                    f"{column_name}: "
                    + ", ".join(
                        str(booking_id)
                        for booking_id in orphan_ids
                    )
                )

        if orphan_messages:
            raise RuntimeError(
                "Нельзя включить внешние ключи bookings: "
                "найдены записи с несуществующими связями. "
                "Первые Booking.id по полям: "
                + "; ".join(orphan_messages)
                + ". Исправьте данные вручную "
                "и повторите запуск."
            )

        for (
            column_name,
            config,
        ) in BOOKING_FOREIGN_KEYS.items():
            foreign_keys = _current_foreign_keys(
                connection,
                column_name,
            )

            if _foreign_key_is_correct(
                foreign_keys,
                config["target_table"],
                config["target_column"],
                config["delete_rule"],
            ):
                logger.info(
                    "FK bookings.%s уже корректен.",
                    column_name,
                )
                continue

            _drop_foreign_keys(
                connection,
                foreign_keys,
            )

            constraint_name = config[
                "constraint_name"
            ]
            target_table = config[
                "target_table"
            ]
            target_column = config[
                "target_column"
            ]
            delete_rule = config[
                "delete_rule"
            ]

            connection.execute(
                text(
                    f"""
                    ALTER TABLE bookings
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column_name})
                    REFERENCES {target_table} ({target_column})
                    ON DELETE {delete_rule}
                    """
                )
            )

            logger.info(
                "FK bookings.%s установлен: "
                "%s(%s), ON DELETE %s.",
                column_name,
                target_table,
                target_column,
                delete_rule,
            )

    logger.info(
        "Целостность внешних ключей Booking проверена."
    )
