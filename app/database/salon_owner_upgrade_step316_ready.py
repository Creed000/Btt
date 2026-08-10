import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)

INDEX_NAME = "uq_salons_active_owner"


def upgrade_active_salon_owner_uniqueness() -> None:
    """
    Гарантирует на уровне БД:
    у одного владельца может быть только один активный салон.

    Неактивные салоны сохраняются как история и не мешают
    владельцу создать/активировать новый салон позже.
    """
    inspector = inspect(engine)

    if "salons" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("salons")
    }

    required = {
        "id",
        "owner_id",
        "is_active",
    }

    if not required.issubset(columns):
        logger.warning(
            "Не удалось создать %s: в salons не хватает колонок %s",
            INDEX_NAME,
            ", ".join(sorted(required - columns)),
        )
        return

    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                """
                SELECT owner_id, COUNT(*) AS active_count
                FROM salons
                WHERE is_active = TRUE
                GROUP BY owner_id
                HAVING COUNT(*) > 1
                ORDER BY owner_id
                """
            )
        ).all()

        if duplicates:
            owners = ", ".join(
                str(row.owner_id)
                for row in duplicates
            )

            raise RuntimeError(
                "Нельзя включить ограничение одного активного салона "
                "на владельца: уже существуют дубли активных салонов "
                f"для owner_id: {owners}. "
                "Сначала деактивируйте лишние салоны."
            )

        dialect = engine.dialect.name

        if dialect == "postgresql":
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON salons (owner_id)
                    WHERE is_active = TRUE
                    """
                )
            )
        elif dialect == "sqlite":
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON salons (owner_id)
                    WHERE is_active = 1
                    """
                )
            )
        else:
            logger.warning(
                "Диалект %s не поддержан для частичного уникального "
                "индекса %s.",
                dialect,
                INDEX_NAME,
            )
            return

    logger.info(
        "Ограничение одного активного салона на владельца проверено."
    )
