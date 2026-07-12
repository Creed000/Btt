from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
    )

    description: Mapped[str | None] = mapped_column(
        String(1000)
    )

    rating: Mapped[float] = mapped_column(default=5.0)

    user = relationship("User")
