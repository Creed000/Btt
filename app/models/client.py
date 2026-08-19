from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint(
            "bonus_points >= 0",
            name="ck_clients_bonus_points_nonnegative",
        ),
        CheckConstraint(
            "total_visits >= 0",
            name="ck_clients_total_visits_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
    )

    bonus_points: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    total_visits: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="client",
    )
