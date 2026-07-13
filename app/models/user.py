from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(String(64))

    first_name: Mapped[str] = mapped_column(String(100))

    last_name: Mapped[str | None] = mapped_column(String(100))

    phone: Mapped[str | None] = mapped_column(String(30))

    language: Mapped[str] = mapped_column(
        String(10),
        default="ru",
    )

    # Роль пользователя
    # client | master | admin | owner
    role: Mapped[str] = mapped_column(
        String(20),
        default="client",
    )

    # Часовой пояс
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Europe/Moscow",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Последняя активность
    last_seen: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
