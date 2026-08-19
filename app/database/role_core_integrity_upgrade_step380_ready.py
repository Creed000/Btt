import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


VALID_ROLES = (
    "client",
    "master",
    "owner",
    "admin",
)

LEGACY_ROLE_MAP = {
    "salon_admin": "owner",
    "super_admin": "admin",
}


def upgrade_role_core_integrity() -> None:
    """
    Синхронизирует legacy Role с фактическим User.role.

    Старые значения:
      salon_admin -> owner
      super_admin -> admin

    Гарантирует:
    - name NOT NULL;
    - допустимые роли только client/master/owner/admin;
    - name уникален.

    Неизвестные значения и конфликты миграции
    автоматически не удаляются.
    """
    inspector = inspect(engine)

    if "roles" not in inspector.get_table_names():
        logger.info(
            "Таблица roles ещё не создана. "
            "Role core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Role core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("roles")
    }

    if "name" not in columns:
        raise RuntimeError(
            "В roles отсутствует обязательная колонка name."
        )

    with engine.begin() as connection:
        rows = list(
            connection.execute(
                text(
                    """
                    SELECT id, name::text AS name
                    FROM roles
                    ORDER BY id
                    """
                )
            ).mappings()
        )

        unknown = [
            row
            for row in rows
            if (
                row["name"] is None
                or row["name"] not in VALID_ROLES
                and row["name"] not in LEGACY_ROLE_MAP
            )
        ]

        if unknown:
            details = "; ".join(
                (
                    f"id={row['id']} "
                    f"name={row['name']!r}"
                )
                for row in unknown[:50]
            )

            raise RuntimeError(
                "Нельзя синхронизировать roles: "
                "найдены неизвестные значения. "
                + details
            )

        current_names = {
            row["name"]
            for row in rows
            if row["name"] is not None
        }

        collisions = []

        for old_name, new_name in LEGACY_ROLE_MAP.items():
            if (
                old_name in current_names
                and new_name in current_names
            ):
                collisions.append(
                    f"{old_name!r} + {new_name!r}"
                )

        if collisions:
            raise RuntimeError(
                "Нельзя автоматически преобразовать legacy roles: "
                "одновременно существуют старое и новое значения: "
                + ", ".join(collisions)
                + ". Объедините записи вручную и повторите запуск."
            )

        # Старые create_all могли создать native PostgreSQL ENUM.
        # Переводим колонку в обычный VARCHAR, чтобы единообразно
        # использовать те же значения, что и User.role.
        connection.execute(
            text(
                """
                ALTER TABLE roles
                ALTER COLUMN name
                TYPE VARCHAR(20)
                USING name::text
                """
            )
        )

        for old_name, new_name in LEGACY_ROLE_MAP.items():
            connection.execute(
                text(
                    """
                    UPDATE roles
                    SET name = :new_name
                    WHERE name = :old_name
                    """
                ),
                {
                    "old_name": old_name,
                    "new_name": new_name,
                },
            )

        duplicate_names = list(
            connection.execute(
                text(
                    """
                    SELECT
                        name,
                        array_agg(id ORDER BY id) AS role_ids
                    FROM roles
                    GROUP BY name
                    HAVING COUNT(*) > 1
                    ORDER BY name
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicate_names:
            details = "; ".join(
                (
                    f"name={row['name']!r} "
                    f"Role.id={list(row['role_ids'])}"
                )
                for row in duplicate_names
            )

            raise RuntimeError(
                "Нельзя включить уникальность Role.name: "
                "найдены дубли после синхронизации. "
                + details
            )

        connection.execute(
            text(
                """
                ALTER TABLE roles
                ALTER COLUMN name SET NOT NULL
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE roles
                DROP CONSTRAINT IF EXISTS
                    ck_roles_name_valid
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE roles
                ADD CONSTRAINT ck_roles_name_valid
                CHECK (
                    name IN (
                        'client',
                        'master',
                        'owner',
                        'admin'
                    )
                )
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_roles_name
                ON roles (name)
                """
            )
        )

    logger.info(
        "Role core integrity синхронизирована."
    )
