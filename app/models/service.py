from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)

    master_id: Mapped[int] = mapped_column(
        ForeignKey("masters.id")
    )

    title: Mapped[str] = mapped_column(
        String(100)
    )

    duration: Mapped[int] = mapped_column(
        Integer
    )

    price: Mapped[int] = mapped_column(
        Integer
    )
