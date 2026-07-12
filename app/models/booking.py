from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id")
    )

    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id")
    )

    booking_time: Mapped[datetime] = mapped_column(
        DateTime
    )

    status: Mapped[str] = mapped_column(default="new")
