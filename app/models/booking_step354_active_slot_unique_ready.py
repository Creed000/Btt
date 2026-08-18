from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'confirmed', 'completed', 'cancelled')",
            name="ck_bookings_status_valid",
        ),
        Index(
            "uq_bookings_active_master_slot",
            "master_id",
            "booking_date",
            "booking_time",
            unique=True,
            postgresql_where=text(
                "status IN ('new', 'confirmed')"
            ),
        ),
        Index(
            "uq_bookings_active_client_slot",
            "client_id",
            "booking_date",
            "booking_time",
            unique=True,
            postgresql_where=text(
                "status IN ('new', 'confirmed')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE")
    )

    # История записи должна сохраняться:
    # услугу нельзя удалить, пока на неё есть Booking.
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT")
    )

    booking_date: Mapped[date] = mapped_column(Date)
    booking_time: Mapped[time] = mapped_column(Time)

    status: Mapped[str] = mapped_column(
        String(20),
        default="new",
        server_default=text("'new'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    # Старые общие флаги сохраняем для совместимости
    # со старыми базами/деплоями.
    reminder_24h_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    reminder_2h_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # Новые раздельные флаги доставки.
    reminder_24h_client_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    reminder_24h_master_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    reminder_2h_client_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    reminder_2h_master_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # Временные атомарные claims защищают от двойной
    # отправки между несколькими Railway-процессами.
    reminder_24h_client_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    reminder_24h_master_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    reminder_2h_client_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    reminder_2h_master_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    client: Mapped["User"] = relationship("User")
    master: Mapped["Master"] = relationship("Master")
    service: Mapped["Service"] = relationship("Service")
