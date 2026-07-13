from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )

    bonus_points: Mapped[int] = mapped_column(default=0)

    total_visits: Mapped[int] = mapped_column(default=0)

    user: Mapped["User"] = relationship(
        "User",
        back_populates="client",
    )
