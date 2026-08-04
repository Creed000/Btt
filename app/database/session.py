from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config.settings import settings


url = make_url(
    settings.DATABASE_URL
)

connect_args: dict[str, object] = {}
engine_options: dict[str, object] = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
}

if url.drivername in {
    "postgresql",
    "postgresql+psycopg",
}:
    if url.drivername == "postgresql":
        url = url.set(
            drivername="postgresql+psycopg"
        )

    # Railway PostgreSQL обычно поддерживает SSL.
    # Если sslmode уже указан в DATABASE_URL, повторно не добавляем.
    if "sslmode" not in url.query:
        connect_args["sslmode"] = "require"

elif url.drivername == "sqlite":
    # Нужно для работы Telegram-бота с SQLite из разных потоков.
    connect_args["check_same_thread"] = False

    # Для SQLite pool_pre_ping не требуется.
    engine_options["pool_pre_ping"] = False

else:
    raise RuntimeError(
        f"Неподдерживаемая база данных: {url.drivername}"
    )


engine = create_engine(
    url,
    connect_args=connect_args,
    **engine_options,
)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
