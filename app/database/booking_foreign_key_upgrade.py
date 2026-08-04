import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


def upgrade_booking_service_foreign_key() -> None:
    """
    Проверяет внешний ключ bookings.service_id.

    Если правило уже RESTRICT или NO ACTION, ничего не меняет.
    Если используется CASCADE или другое правило, заменяет его
    на ON DELETE RESTRICT.
    """
    if engine.dialect.name != "postgresql":
        logger.info(
            "Обновление FK bookings.service_id пропущено: "
            "используется не PostgreSQL."
        )
        return

    inspector = inspect(engine)

    if "bookings" not in inspector.get_table_names():
        logger.info(
            "Таблица bookings ещё не создана. "
            "Обновление внешнего ключа пропущено."
        )
        return

    with engine.begin() as connection:
        foreign_keys = list(
            connection.execute(
                text(
                    """
                    SELECT
                        tc.constraint_name,
                        rc.delete_rule
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.constraint_schema = kcu.constraint_schema
                    JOIN information_schema.referential_constraints AS rc
                      ON tc.constraint_name = rc.constraint_name
                     AND tc.constraint_schema = rc.constraint_schema
                    WHERE tc.table_schema = current_schema()
                      AND tc.table_name = 'bookings'
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND kcu.column_name = 'service_id'
                    """
                )
            ).mappings()
        )

        if (
            len(foreign_keys) == 1
            and foreign_keys[0]["delete_rule"] in {
                "RESTRICT",
                "NO ACTION",
            }
        ):
            logger.info(
                "Внешний ключ bookings.service_id уже безопасен: %s.",
                foreign_keys[0]["delete_rule"],
            )
            return

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

        connection.execute(
            text(
                """
                ALTER TABLE bookings
                ADD CONSTRAINT fk_bookings_service_id
                FOREIGN KEY (service_id)
                REFERENCES services (id)
                ON DELETE RESTRICT
                """
            )
        )

    logger.info(
        "Внешний ключ bookings.service_id обновлён: "
        "ON DELETE RESTRICT."
    )
