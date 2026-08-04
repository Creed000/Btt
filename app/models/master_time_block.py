from datetime import date, time

from sqlalchemy import Date, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MasterTimeBlock(Base):
    __tablename__ = "master_time_blocks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    master_id: Mapped[int] = mapped_column(
        ForeignKey(
            "masters.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    block_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    master = relationship(
        "Master",
        back_populates="time_blocks",
    )
