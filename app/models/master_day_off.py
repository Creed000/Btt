from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MasterDayOff(Base):
    __tablename__ = "master_days_off"
    __table_args__ = (
        UniqueConstraint(
            "master_id",
            "day_off_date",
            name="uq_master_day_off_date",
        ),
    )

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

    day_off_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    master = relationship(
        "Master",
        back_populates="days_off",
    )
