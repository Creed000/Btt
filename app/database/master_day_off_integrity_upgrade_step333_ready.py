import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "uq_master_days_off_master_date"


def upgrade_master_day_off_integrity() -> None:
    """
    Гарантирует одну строку выходного на master_id + day_off_date
    для уже существующих production-баз.

    Существующие дубли автоматически не удаляются.
    """
    inspector = inspect(engine)

    if "master_days_off" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("master_days_off")
    }

    required = {"id", "master_id", "day_off_date"}
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось усилить master_days_off: отсутствуют колонки %s",
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        duplicates = connection.execute(
            text(
                """
                SELECT
                    master_id,
                    day_off_date,
                    COUNT(*) AS duplicate_count
                FROM master_days_off
                GROUP BY master_id, day_off_date
                HAVING COUNT(*) > 1
                ORDER BY master_id, day_off_date
                LIMIT 20
                """
            )
        ).all()

        if duplicates:
            details = "; ".join(
                (
                    f"master_id={row.master_id}, "
                    f"date={row.day_off_date}, "
                    f"count={row.duplicate_count}"
                )
                for row in duplicates
            )
            raise RuntimeError(
                "Нельзя включить уникальность выходных дат: "
                "в БД уже есть дубли master_id + day_off_date. "
                f"Найдены: {details}"
            )

        if engine.dialect.name in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON master_days_off (master_id, day_off_date)
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
        "Уникальность master_days_off(master_id, day_off_date) проверена."
    )
