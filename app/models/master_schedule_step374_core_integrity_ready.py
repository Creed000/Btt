from datetime import time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MasterSchedule(Base):
    __tablename__ = "master_schedules"
    __table_args__ = (
        UniqueConstraint(
            "master_id",
            "weekday",
            name="uq_master_schedule_weekday",
        ),
        CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_master_schedules_weekday_range",
        ),
        CheckConstraint(
            "work_start < work_end",
            name="ck_master_schedules_work_time_order",
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

    # 0 — понедельник, 6 — воскресенье.
    weekday: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    work_start: Mapped[time] = mapped_column(
        Time,
        default=time(hour=9),
        server_default=text("'09:00:00'"),
        nullable=False,
    )

    work_end: Mapped[time] = mapped_column(
        Time,
        default=time(hour=18),
        server_default=text("'18:00:00'"),
        nullable=False,
    )

    is_working: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )

    master = relationship(
        "Master",
        back_populates="schedules",
    )
