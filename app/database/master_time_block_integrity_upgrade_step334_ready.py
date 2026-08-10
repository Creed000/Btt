import logging

from sqlalchemy import inspect, text

from app.database.session import engine


logger = logging.getLogger(__name__)
INDEX_NAME = "ix_master_time_blocks_master_date"


def upgrade_master_time_block_integrity() -> None:
    """
    Проверяет существующие блокировки времени.

    Инварианты:
    - start_time < end_time;
    - блокировки одного master_id на одну дату не пересекаются.

    Старые данные автоматически не удаляются и не объединяются.
    """
    inspector = inspect(engine)

    if "master_time_blocks" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("master_time_blocks")
    }

    required = {
        "id",
        "master_id",
        "block_date",
        "start_time",
        "end_time",
    }
    missing = required - columns

    if missing:
        logger.warning(
            "Не удалось проверить master_time_blocks: отсутствуют %s",
            ", ".join(sorted(missing)),
        )
        return

    with engine.begin() as connection:
        invalid = connection.execute(
            text(
                """
                SELECT id, master_id, block_date, start_time, end_time
                FROM master_time_blocks
                WHERE start_time >= end_time
                ORDER BY master_id, block_date, start_time, id
                LIMIT 20
                """
            )
        ).all()

        if invalid:
            details = "; ".join(
                (
                    f"id={row.id}, master_id={row.master_id}, "
                    f"date={row.block_date}, "
                    f"{row.start_time}-{row.end_time}"
                )
                for row in invalid
            )
            raise RuntimeError(
                "В master_time_blocks найдены некорректные интервалы "
                "(start_time >= end_time). "
                f"Найдены: {details}"
            )

        overlaps = connection.execute(
            text(
                """
                SELECT
                    a.id AS first_id,
                    b.id AS second_id,
                    a.master_id,
                    a.block_date
                FROM master_time_blocks a
                JOIN master_time_blocks b
                  ON b.master_id = a.master_id
                 AND b.block_date = a.block_date
                 AND b.id > a.id
                 AND a.start_time < b.end_time
                 AND b.start_time < a.end_time
                ORDER BY a.master_id, a.block_date, a.id, b.id
                LIMIT 20
                """
            )
        ).all()

        if overlaps:
            details = "; ".join(
                (
                    f"master_id={row.master_id}, date={row.block_date}, "
                    f"blocks=#{row.first_id}/#{row.second_id}"
                )
                for row in overlaps
            )
            raise RuntimeError(
                "В master_time_blocks найдены пересекающиеся блокировки. "
                f"Найдены: {details}"
            )

        if engine.dialect.name in {"postgresql", "sqlite"}:
            connection.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS {INDEX_NAME}
                    ON master_time_blocks (master_id, block_date)
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
        "Целостность master_time_blocks проверена."
    )
