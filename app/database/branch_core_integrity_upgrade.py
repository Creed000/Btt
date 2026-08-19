import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)


CORE_COLUMNS = (
    "salon_id",
    "name",
    "address",
)


def upgrade_branch_core_integrity() -> None:
    """
    Укрепляет существующую таблицу branches.

    Гарантирует:
    - salon_id/name/address NOT NULL;
    - name/address не пустые после TRIM;
    - salon_id ссылается на существующий Salon;
    - нормализованная уникальность имени внутри салона
      остаётся под branch_unique_upgrade.

    Повреждённые данные автоматически не исправляются.
    """
    inspector = inspect(engine)

    if "branches" not in inspector.get_table_names():
        logger.info(
            "Таблица branches ещё не создана. "
            "Branch core integrity upgrade пропущен."
        )
        return

    if engine.dialect.name != "postgresql":
        logger.info(
            "Branch core integrity upgrade пропущен для %s.",
            engine.dialect.name,
        )
        return

    tables = set(inspector.get_table_names())

    if "salons" not in tables:
        raise RuntimeError(
            "Нельзя включить Branch core integrity: "
            "таблица salons отсутствует."
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("branches")
    }

    missing_columns = [
        name
        for name in CORE_COLUMNS
        if name not in columns
    ]

    if missing_columns:
        raise RuntimeError(
            "В branches отсутствуют обязательные поля: "
            + ", ".join(missing_columns)
        )

    with engine.begin() as connection:
        broken = list(
            connection.execute(
                text(
                    """
                    SELECT id, salon_id, name, address
                    FROM branches
                    WHERE salon_id IS NULL
                       OR name IS NULL
                       OR LENGTH(TRIM(name)) = 0
                       OR address IS NULL
                       OR LENGTH(TRIM(address)) = 0
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
                    f"salon_id={row['salon_id']} "
                    f"name={row['name']!r} "
                    f"address={row['address']!r}"
                )
                for row in broken
            )

            raise RuntimeError(
                "Нельзя включить Branch core integrity: "
                "найдены NULL/пустые значения. "
                + details
            )

        orphan_ids = list(
            connection.execute(
                text(
                    """
                    SELECT b.id
                    FROM branches AS b
                    LEFT JOIN salons AS s
                      ON s.id = b.salon_id
                    WHERE s.id IS NULL
                    ORDER BY b.id
                    LIMIT 50
                    """
                )
            ).scalars()
        )

        if orphan_ids:
            raise RuntimeError(
                "Нельзя включить FK branches.salon_id: "
                "найдены сиротские Branch.id="
                + ", ".join(
                    str(item)
                    for item in orphan_ids
                )
            )

        for column_name in CORE_COLUMNS:
            connection.execute(
                text(
                    f"""
                    ALTER TABLE branches
                    ALTER COLUMN {column_name} SET NOT NULL
                    """
                )
            )

        for constraint_name in (
            "ck_branches_name_not_blank",
            "ck_branches_address_not_blank",
        ):
            connection.execute(
                text(
                    f"""
                    ALTER TABLE branches
                    DROP CONSTRAINT IF EXISTS {constraint_name}
                    """
                )
            )

        connection.execute(
            text(
                """
                ALTER TABLE branches
                ADD CONSTRAINT ck_branches_name_not_blank
                CHECK (LENGTH(TRIM(name)) > 0)
                """
            )
        )

        connection.execute(
            text(
                """
                ALTER TABLE branches
                ADD CONSTRAINT ck_branches_address_not_blank
                CHECK (LENGTH(TRIM(address)) > 0)
                """
            )
        )

    logger.info(
        "Branch core integrity включена."
    )
