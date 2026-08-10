import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_branches_salon_normalized_name"


def upgrade_branch_name_uniqueness() -> None:
    """
    Не допускает два филиала одного салона,
    отличающиеся только регистром или пробелами.
    """
    inspector = inspect(engine)

    if "branches" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("branches")
    }

    required = {"id", "salon_id", "name"}
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось создать %s: в branches не хватает %s",
            INDEX_NAME,
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                """
                SELECT
                    salon_id,
                    LOWER(TRIM(name)) AS normalized_name,
                    COUNT(*) AS duplicate_count
                FROM branches
                GROUP BY salon_id, LOWER(TRIM(name))
                HAVING COUNT(*) > 1
                ORDER BY salon_id, normalized_name
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                (
                    f"salon_id={row.salon_id}, "
                    f"name={row.normalized_name!r}, "
                    f"count={row.duplicate_count}"
                )
                for row in duplicates[:20]
            )
            raise RuntimeError(
                "Нельзя включить уникальность филиалов: "
                "в БД уже есть дубли названий внутри одного салона. "
                f"Найдены: {details}"
            )

        if engine.dialect.name in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON branches (salon_id, LOWER(TRIM(name)))
                    """
                )
            )
        else:
            logger.warning(
                "Диалект %s не поддержан для индекса %s.",
                engine.dialect.name,
                INDEX_NAME,
            )
            return

    logger.info(
        "Уникальность названий филиалов внутри салона проверена."
    )
