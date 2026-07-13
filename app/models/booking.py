from datetime import datetime, date, time

from sqlalchemy import Date, Time, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id", ondelete="CASCADE")
    )

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )

    booking_date: Mapped[date] = mapped_column(
        Date
    )

    booking_time: Mapped[time] = mapped_column(
        Time
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="new",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    client: Mapped["User"] = relationship("User")

    master: Mapped["Master"] = relationship("Master")

    service: Mapped["Service"] = relationship("Service")
