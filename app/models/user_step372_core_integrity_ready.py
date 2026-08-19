from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "telegram_id > 0",
            name="ck_users_telegram_id_positive",
        ),
        CheckConstraint(
            "LENGTH(TRIM(first_name)) > 0",
            name="ck_users_first_name_not_blank",
        ),
        CheckConstraint(
            "language IN ('ru', 'ky', 'en')",
            name="ck_users_language_valid",
        ),
        CheckConstraint(
            "role IN ('client', 'master', 'owner', 'admin')",
            name="ck_users_role_valid",
        ),
        CheckConstraint(
            "LENGTH(TRIM(timezone)) > 0",
            name="ck_users_timezone_not_blank",
        ),
    )

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
        server_default=text("'ru'"),
        nullable=False,
    )

    # client | master | admin | owner
    role: Mapped[str] = mapped_column(
        String(20),
        default="client",
        server_default=text("'client'"),
        nullable=False,
    )

    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Asia/Bishkek",
        server_default=text("'Asia/Bishkek'"),
        nullable=False,
    )

    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
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
