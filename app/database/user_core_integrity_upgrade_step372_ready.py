import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_COLUMNS = (
    "telegram_id",
    "first_name",
    "language",
    "role",
    "timezone",
    "notifications_enabled",
    "is_active",
    "created_at",
    "last_seen",
)


def _has_unique_telegram_id(connection) -> bool:
    inspector = inspect(connection)

    for constraint in inspector.get_unique_constraints("users"):
        columns = constraint.get("column_names") or []
        if columns == ["telegram_id"]:
            return True

    for index in inspector.get_indexes("users"):
        columns = index.get("column_names") or []
        if index.get("unique") and columns == ["telegram_id"]:
            return True

    return False


def upgrade_user_core_integrity() -> None:
    """
    Укрепляет существующую таблицу users в PostgreSQL.

    Гарантирует:
    - обязательные core-поля NOT NULL;
    - telegram_id > 0 и уникален;
    - first_name/timezone не пустые;
    - language только ru/ky/en;
    - role только client/master/owner/admin;
    - DB defaults для language/role/timezone/notifications/is_active.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "users" not in inspector.get_table_names():
        logger.info(
            "Таблица users ещё не создана. "
            "User core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "User core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("users")
    }

    missing = [
        name for name in CORE_COLUMNS
        if name not in columns
    ]

    if missing:
        raise RuntimeError(
            "В users отсутствуют обязательные поля: "
            + ", ".join(missing)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT
                        id,
                        telegram_id,
                        first_name,
                        language,
                        role,
                        timezone
                    FROM users
                    WHERE telegram_id IS NULL
                       OR telegram_id <= 0
                       OR first_name IS NULL
                       OR LENGTH(TRIM(first_name)) = 0
                       OR language IS NULL
                       OR language NOT IN ('ru', 'ky', 'en')
                       OR role IS NULL
                       OR role NOT IN ('client', 'master', 'owner', 'admin')
                       OR timezone IS NULL
                       OR LENGTH(TRIM(timezone)) = 0
                       OR notifications_enabled IS NULL
                       OR is_active IS NULL
                       OR created_at IS NULL
                       OR last_seen IS NULL
                    ORDER BY id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if broken:
            details = "; ".join(
                (
                    f"id={row['id']} "
                    f"telegram_id={row['telegram_id']} "
                    f"language={row['language']!r} "
                    f"role={row['role']!r}"
                )
                for row in broken
            )

            raise RuntimeError(
                "Нельзя включить User core integrity: "
                "найдены некорректные строки. "
                + details
            )

        duplicates = list(
            connection.execute(
                text(
                    """
                    SELECT
                        telegram_id,
                        array_agg(id ORDER BY id) AS user_ids
                    FROM users
                    GROUP BY telegram_id
                    HAVING COUNT(*) > 1
                    ORDER BY telegram_id
                    LIMIT 50
                    """
                )
            ).mappings()
        )

        if duplicates:
            details = "; ".join(
                (
                    f"telegram_id={row['telegram_id']} "
                    f"User.id={list(row['user_ids'])}"
                )
                for row in duplicates
            )

            raise RuntimeError(
                "Нельзя включить уникальность users.telegram_id: "
                "найдены дубли. "
                + details
            )

        for column_name in CORE_COLUMNS:
            connection.execute(
                text(
                    f"ALTER TABLE users "
                    f"ALTER COLUMN {column_name} SET NOT NULL"
                )
            )

        defaults = {
            "language": "'ru'",
            "role": "'client'",
            "timezone": "'Asia/Bishkek'",
            "notifications_enabled": "true",
            "is_active": "true",
        }

        for column_name, sql_default in defaults.items():
            connection.execute(
                text(
                    f"ALTER TABLE users "
                    f"ALTER COLUMN {column_name} "
                    f"SET DEFAULT {sql_default}"
                )
            )

        constraints = {
            "ck_users_telegram_id_positive":
                "CHECK (telegram_id > 0)",
            "ck_users_first_name_not_blank":
                "CHECK (LENGTH(TRIM(first_name)) > 0)",
            "ck_users_language_valid":
                "CHECK (language IN ('ru', 'ky', 'en'))",
            "ck_users_role_valid":
                "CHECK (role IN ('client', 'master', 'owner', 'admin'))",
            "ck_users_timezone_not_blank":
                "CHECK (LENGTH(TRIM(timezone)) > 0)",
        }

        for name, sql in constraints.items():
            connection.execute(
                text(
                    f"ALTER TABLE users "
                    f"DROP CONSTRAINT IF EXISTS {name}"
                )
            )
            connection.execute(
                text(
                    f"ALTER TABLE users "
                    f"ADD CONSTRAINT {name} {sql}"
                )
            )

        if not _has_unique_telegram_id(connection):
            connection.execute(
                text(
                    """
                    CREATE UNIQUE INDEX
                        uq_users_telegram_id
                    ON users (telegram_id)
                    """
                )
            )

    logger.info(
        "User core integrity включена."
    )
