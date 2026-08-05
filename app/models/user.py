from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(64)
    )

    first_name: Mapped[str] = mapped_column(
        String(100)
    )

    last_name: Mapped[str | None] = mapped_column(
        String(100)
    )

    phone: Mapped[str | None] = mapped_column(
        String(30)
    )

    language: Mapped[str] = mapped_column(
        String(10),
        default="ru",
        nullable=False,
    )

    # client | master | admin | owner
    role: Mapped[str] = mapped_column(
        String(20),
        default="client",
        nullable=False,
    )

    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Asia/Bishkek",
        nullable=False,
    )

    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_seen: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    master = relationship(
        "Master",
        back_populates="user",
        uselist=False,
    )

    client: Mapped["Client"] = relationship(
        "Client",
        back_populates="user",
        uselist=False,
    )
